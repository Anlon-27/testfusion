"""
RAG 检索引擎
基于 ChromaDB 的知识库检索增强生成模块
使用本地 sentence-transformers 模型进行 Embedding，完全离线运行
"""

import os
import re
import json
import uuid
import logging
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import chromadb
from chromadb import EmbeddingFunction

logger = logging.getLogger(__name__)

# 默认向量数据库路径
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'vector_db'
)

DEFAULT_DOC_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'data', 'raw_files'
)

os.makedirs(DEFAULT_DOC_PATH, exist_ok=True)


class LocalEmbeddingFunction(EmbeddingFunction):
    """基于 sentence-transformers 的本地 Embedding 函数

    完全离线运行，不依赖外部 API。默认使用 paraphrase-multilingual-MiniLM-L12-v2
    多语言模型（支持中文），首次使用时会自动下载。
    """

    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                logger.info(f"本地 Embedding 模型已加载: {self.model_name}")
            except Exception as e:
                logger.error(f"加载本地 Embedding 模型失败: {e}")
                raise
        return self._model

    def __call__(self, input: List[str]) -> List[List[float]]:
        if isinstance(input, str):
            input = [input]
        if not input:
            return []

        model = self._get_model()
        embeddings = model.encode(input, show_progress_bar=False)
        return embeddings.tolist()


class TextSplitter:
    """打磨后的智能语义/段落文本切片器"""

    @staticmethod
    def recursive_split(text: str, chunk_size: int = 600, chunk_overlap: int = 150) -> List[str]:
        if not text:
            return []

        # 1. 预处理：按段落（\n\n 或 \r\n\r\n）进行初步拆分，这能最大限度保留段落和表格的完整性
        paragraphs = re.split(r'\n\s*\n', text)
        chunks = []
        current_chunk = []
        current_len = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_len = len(para)

            # 2. 如果单段已经超过了 chunk_size，需要对单段进行句级切分
            if para_len > chunk_size:
                # 如果当前 buffer 里还有内容，先存成一个块
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_len = 0

                # 对这个长段按句切分
                sentences = re.split(r'(?<=[。！？\n])', para)
                sub_chunk = []
                sub_len = 0
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    if sub_len + len(sentence) > chunk_size:
                        if sub_chunk:
                            chunks.append(" ".join(sub_chunk))
                        # 为了处理 overlap，保留末尾句
                        overlap_candidates = []
                        overlap_len = 0
                        for s in reversed(sub_chunk):
                            if overlap_len + len(s) < chunk_overlap:
                                overlap_candidates.insert(0, s)
                                overlap_len += len(s)
                            else:
                                break
                        sub_chunk = overlap_candidates + [sentence]
                        sub_len = overlap_len + len(sentence)
                    else:
                        sub_chunk.append(sentence)
                        sub_len += len(sentence)
                if sub_chunk:
                    chunks.append(" ".join(sub_chunk))
            
            # 3. 正常情况下，累加段落，防止段落被无情截断
            elif current_len + para_len + 2 > chunk_size:
                # 存入当前累加的块
                chunks.append("\n\n".join(current_chunk))
                
                # 处理 overlap
                overlap_chunk = []
                overlap_len = 0
                for p in reversed(current_chunk):
                    if overlap_len + len(p) + 2 < chunk_overlap:
                        overlap_chunk.insert(0, p)
                        overlap_len += len(p) + 2
                    else:
                        break
                
                current_chunk = overlap_chunk + [para]
                current_len = overlap_len + para_len
            else:
                current_chunk.append(para)
                current_len += para_len + (2 if current_len > 0 else 0)

        # 存入最后的残留块
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks


class RAGEngine:
    """RAG 检索引擎

    基于 ChromaDB 的向量检索，支持知识库、历史用例的增删查改，
    以及 LLM 智能过滤去噪。
    """

    def __init__(
        self,
        db_path: str = None,
    ):
        self.db_path = db_path or DEFAULT_DB_PATH
        os.makedirs(self.db_path, exist_ok=True)

        self.client = chromadb.PersistentClient(path=self.db_path)
        self.embedding_fn = LocalEmbeddingFunction()

        self.knowledge_coll = self.client.get_or_create_collection(
            name="company_knowledge",
            embedding_function=self.embedding_fn,
        )
        self.history_coll = self.client.get_or_create_collection(
            name="history_cases",
            embedding_function=self.embedding_fn,
        )

    # ---- 知识库管理 ----

    def add_knowledge(
        self,
        content: str,
        source_name: str = "unknown",
        summary: str = "",
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ) -> tuple:
        """将文本切片后存入知识库

        Returns:
            (doc_id, chunk_count): 文档唯一标识和切片数量
        """
        chunks = TextSplitter.recursive_split(content, chunk_size, chunk_overlap)
        file_doc_id = str(uuid.uuid4())
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

        ids = []
        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{file_doc_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "doc_id": file_doc_id,
                "source": source_name,
                "summary": summary or "暂无摘要",
                "chunk_index": i,
                "type": "spec",
                "date": current_time,
            })

        self.knowledge_coll.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info(f"知识库新增文档 {source_name}，共 {len(chunks)} 个切片，doc_id={file_doc_id}")
        return file_doc_id, len(chunks)

    def add_history_case(self, prd_text: str, case_json: Any, summary: str = "") -> str:
        """存入历史测试用例（不切片，整体存储）"""
        if isinstance(case_json, (dict, list)):
            case_json = json.dumps(case_json, ensure_ascii=False)

        doc_id = str(uuid.uuid4())
        self.history_coll.add(
            documents=[prd_text],
            metadatas=[{
                "doc_id": doc_id,
                "answer": case_json,
                "source": summary,
                "summary": summary,
                "type": "history",
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }],
            ids=[doc_id],
        )
        return doc_id

    # ---- 检索 ----

    def search_context(
        self,
        query: str,
        use_history: bool = True,
        use_knowledge: bool = True,
        top_k_knowledge: int = 3,
        top_k_history: int = 1,
    ) -> Tuple[str, List[str]]:
        """多路检索：知识库 + 历史用例

        Returns:
            (context_text, sources_list): 拼接后的上下文文本和来源列表
        """
        context_parts = []
        sources = []

        if use_knowledge:
            res_k = self.knowledge_coll.query(
                query_texts=[query], n_results=top_k_knowledge
            )
            if res_k.get('documents') and res_k['documents'][0]:
                for i, doc in enumerate(res_k['documents'][0]):
                    meta = res_k['metadatas'][0][i] if res_k.get('metadatas') else {}
                    src = meta.get('source', 'unknown')
                    context_parts.append(f"【技术规范片段 ({src})】:\n...{doc}...")
                    sources.append(src)

        if use_history:
            res_h = self.history_coll.query(
                query_texts=[query], n_results=top_k_history
            )
            if res_h.get('documents') and res_h['documents'][0]:
                for i, doc in enumerate(res_h['documents'][0]):
                    meta = res_h['metadatas'][0][i] if res_h.get('metadatas') else {}
                    summary = meta.get('summary', '历史案例')
                    ans = meta.get('answer', '')
                    context_parts.append(
                        f"【参考历史 ({summary})】:\n参考用例:{ans[:800]}..."
                    )
                    sources.append(summary)

        return "\n\n<<<RAG_SEP>>>\n\n".join(context_parts), list(set(sources))

    async def filter_rag_context(
        self,
        query: str,
        raw_context: str,
        llm_api_key: str,
        llm_base_url: str,
        llm_model_name: str,
    ) -> str:
        """使用 LLM 对检索结果做智能去噪过滤

        调用配置好的大模型 API 清洗 RAG 上下文，只保留与需求相关的部分。
        """
        if not raw_context:
            return ""

        filter_prompt = f"""【任务】
你是一个严格的文档质检员。用户正在为一个软件需求文档 (PRD) 寻找相关的技术规范或历史案例。
现在的检索系统返回了一些片段，其中可能包含大量无关的噪音（如百科知识、小说、无关新闻等）。

【输入信息】
1. 用户的需求摘要：
{query[:2000]}
2. 待筛选的检索片段（片段之间由 <<<RAG_SEP>>> 分隔）：
{raw_context}

【要求】
1. 请仔细阅读检索片段，判断其是否与用户的需求**技术相关**。
2. **只保留**有用的技术规范、业务规则或测试经验，注意 **<<<RAG_SEP>>>** 是不同文档的分隔符，不需要清洗掉。
3. **坚决剔除**任何与软件开发无关的内容。
4. 如果所有片段都无关，请输出 "无相关参考资料"。
5. 直接输出清洗后的纯文本内容，不要包含任何解释。"""

        messages = [
            {"role": "system", "content": "你是一个严格的文档质检员，帮助过滤和清洗技术检索结果。"},
            {"role": "user", "content": filter_prompt},
        ]

        url = llm_base_url.rstrip('/')
        if not url.endswith('/chat/completions'):
            if url.endswith('/v1'):
                url = f"{url}/chat/completions"
            else:
                url = f"{url}/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {llm_api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": llm_model_name,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.1,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()
                return result['choices'][0]['message']['content']
        except Exception as e:
            logger.warning(f"RAG 过滤 LLM 调用失败: {e}，返回原始上下文")
            return raw_context

    # ---- 文档管理 ----

    def list_documents(self, collection_type: str = "knowledge") -> List[Dict[str, Any]]:
        coll = self.history_coll if collection_type == "history" else self.knowledge_coll
        data = coll.get()
        unique_docs = {}
        if data.get('ids'):
            for i, _ in enumerate(data['ids']):
                meta = data['metadatas'][i]
                doc_id = meta.get('doc_id', data['ids'][i])
                if doc_id not in unique_docs:
                    unique_docs[doc_id] = {
                        "doc_id": doc_id,
                        "source": meta.get('source', 'unknown'),
                        "summary": meta.get('summary', '-'),
                        "type": "历史用例" if collection_type == "history" else "技术文档",
                        "date": meta.get('date', '-'),
                    }
        return list(unique_docs.values())

    def get_doc_content(self, doc_id: str, collection_type: str = "knowledge") -> str:
        coll = self.history_coll if collection_type == "history" else self.knowledge_coll
        try:
            items = coll.get(where={"doc_id": doc_id}, limit=1)
            if not items.get('ids'):
                items = coll.get(ids=[doc_id], limit=1)
            if items.get('documents') and items['documents'][0]:
                if collection_type == "history" and items.get('metadatas'):
                    json_str = items['metadatas'][0].get('answer', '{}')
                    try:
                        parsed = json.loads(json_str)
                        return json.dumps(parsed, indent=2, ensure_ascii=False)
                    except json.JSONDecodeError:
                        return json_str
                return items['documents'][0]
        except Exception as e:
            logger.warning(f"获取文档内容失败: {e}")
        return "无法获取文档内容"

    def delete_document(self, doc_id: str, collection_type: str = "knowledge"):
        coll = self.history_coll if collection_type == "history" else self.knowledge_coll
        coll.delete(where={"doc_id": doc_id})
        coll.delete(ids=[doc_id])
        logger.info(f"已删除文档 {doc_id}（{collection_type}）")

    @classmethod
    def get_or_create_engine(
        cls,
        db_path: str = None,
    ) -> 'RAGEngine':
        """工厂方法：缓存单例或者每次都新建（不影响多线程安全）"""
        return cls(
            db_path=db_path,
        )
