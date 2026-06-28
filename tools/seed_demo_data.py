import os
import django
django.setup()

from django.utils import timezone
from django.contrib.auth.hashers import make_password

from apps.users.models import User
from apps.projects.models import Project, ProjectMember, ProjectEnvironment
from apps.versions.models import Version
from apps.testcases.models import TestCase, TestCaseStep
from apps.executions.models import TestPlan, TestRun, TestRunCase
from apps.reviews.models import TestCaseReview, ReviewAssignment, ReviewTemplate
from apps.requirement_analysis.models import (
    RequirementDocument, RequirementAnalysis, BusinessRequirement, 
    GeneratedTestCase, AnalysisTask, AIModelConfig, PromptConfig
)

# 1. 保护并重置唯一的超级管理员，删除其他残留的临时用户
User.objects.exclude(username='admin').delete()
admin = User.objects.filter(username='admin').first()
if not admin:
    admin = User.objects.create_superuser('admin', 'admin@example.com', 'admin123456')
else:
    admin.password = make_password('admin123456')
    admin.is_active = True
    admin.save()
print("管理员重置完成：admin / admin123456")

# 2. 依次清空系统各个子业务板块的冗余与测试数据
ProjectEnvironment.objects.all().delete()
ProjectMember.objects.all().delete()
Version.objects.all().delete()
TestCaseStep.objects.all().delete()
TestCase.objects.all().delete()
TestPlan.objects.all().delete()
TestRunCase.objects.all().delete()
TestRun.objects.all().delete()
ReviewAssignment.objects.all().delete()
TestCaseReview.objects.all().delete()
ReviewTemplate.objects.all().delete()
RequirementDocument.objects.all().delete()
RequirementAnalysis.objects.all().delete()
BusinessRequirement.objects.all().delete()
GeneratedTestCase.objects.all().delete()
AnalysisTask.objects.all().delete()
Project.objects.all().delete()
print("历史残留测试数据清空完成")

# 3. 创建极具专业感的黄金电商展示项目
project = Project.objects.create(
    name="TestFusion Demo - 智能电商质量平台",
    description="面向登录、下单、支付、订单履约的全链路质量保障项目，用于演示 AI 用例生成、接口自动化、UI/APP 自动化、RAG 评审与数据工厂能力。",
    status="active",
    owner=admin
)
ProjectMember.objects.create(project=project, user=admin, role="owner")
print("黄金展示项目创建完成")

# 4. 创建与之配套的项目 Mock 联调环境
env = ProjectEnvironment.objects.create(
    project=project,
    name="Mock 联调环境",
    base_url="http://127.0.0.1:9000",
    description="连接本地 OpenAI 兼容 Mock 服务，用于稳定验证 AI 生成、评审、异常重试链路。",
    variables={
        "api_base_url": "https://demo-api.testfusion.local",
        "web_base_url": "https://shop.testfusion.local",
        "mock_model": "mock-chat",
        "ai_base_url": "http://127.0.0.1:9000",
        "app_package": "com.testfusion.mall"
    },
    is_default=True
)
print("黄金联调环境创建完成")

# 5. 创建演示用基线版本
version = Version.objects.create(
    name="V2.8.0 智能登录与订单全链路",
    description="支持AI辅助测试用例的自愈落库，增加离线ChromaDB一阶段与二阶段余弦重排的离线RAG检索能力。",
    is_baseline=True,
    created_by=admin
)
version.projects.add(project)
print("黄金版本创建完成")

# 6. 设计生成 5 条最高页面水准的覆盖全链路业务演示用例
cases_data = [
    {
        "title": "用户会员中心-密码登录验证",
        "preconditions": "用户已经在系统完成账号密码注册，且账号处于正常激活状态。",
        "steps": "1. 访问 TestFusion 智能电商平台登录页面；\n2. 输入正确用户名 'admin' 和密码 'admin123456'；\n3. 点击 '登录' 按钮并观察页面响应。",
        "expected_result": "系统登录成功，页面顶部右上角显示登录名 'admin'，本地 localStorage 自动更新并保存 JWT access_token 凭证，重定向至系统管理首页。",
        "priority": "critical",
        "test_type": "functional"
    },
    {
        "title": "商品详情页-购物车加入与数量累加",
        "preconditions": "用户处于登录状态，选择了一款有库存的商品。",
        "steps": "1. 在商品详情页点击 '加入购物车' 按钮；\n2. 点击右上角购物车图标查看商品详情；\n3. 再次在详情页点击 '加入购物车'，验证数量累加。",
        "expected_result": "商品成功加入购物车，右上角购物车小红点数量提示 +1；再次加入后，购物车内该商品数量累加为 2，总价按比例正确折算更新。",
        "priority": "high",
        "test_type": "functional"
    },
    {
        "title": "购物车结算-创建待支付订单",
        "preconditions": "用户购物车中已成功添加至少一件有效商品，网络连接正常。",
        "steps": "1. 进入购物车列表页面，选中目标商品；\n2. 点击 '立即结算' 按钮进入订单确认页；\n3. 核对收货人及地址，点击 '提交订单' 并跳转收银台。",
        "expected_result": "订单提交成功，后端逻辑生成待支付订单状态为 'PENDING_PAY'，分配唯一订单流水号，页面安全跳转至统一收银台支付通道，收银台展示对应应付金额。",
        "priority": "critical",
        "test_type": "functional"
    },
    {
        "title": "收银台支付-支付宝沙箱扫码与回调",
        "preconditions": "生成待支付订单，跳转至统一收银台，支付宝沙箱环境可用。",
        "steps": "1. 在收银台选择 '支付宝' 作为支付渠道；\n2. 使用支付宝沙箱测试账号登录并扫码支付；\n3. 模拟支付成功，等待后端接收支付宝异步回调通知并处理。",
        "expected_result": "收银台显示 '支付成功'；后端正确接收并验证支付宝签名回调，订单状态变更为 'PAID' (已支付)，并发起库存实际扣减与短信状态发送通知。",
        "priority": "critical",
        "test_type": "integration"
    },
    {
        "title": "下单交易接口-500并发/秒高频压力测试",
        "preconditions": "测试环境已部署监控组件，Redis 缓存预热完毕，模拟高并发下单接口请求。",
        "steps": "1. 使用 JMeter 脚本对 '/api/order/create/' 发起 500 并发/秒的瞬时下单请求；\n2. 统计接口在 30 秒内的平均响应时间（RT）、吞吐量（TPS）和错误率（Error Rate）。",
        "expected_result": "在高并发流量下，下单接口平均响应时间 (RT) < 180ms，吞吐量正常稳定在限流阈值内，系统无死锁及数据库连接溢出，无超卖事故发生，错误率 < 0.1%。",
        "priority": "high",
        "test_type": "performance"
    }
]

created_cases = []
for c_info in cases_data:
    tc = TestCase.objects.create(
        project=project,
        title=c_info["title"],
        preconditions=c_info["preconditions"],
        steps=c_info["steps"],
        expected_result=c_info["expected_result"],
        priority=c_info["priority"],
        status="active",
        test_type=c_info["test_type"],
        author=admin
    )
    tc.versions.add(version)
    created_cases.append(tc)
print("黄金演示用例生成完成")

# 7. 创建测试计划
plan = TestPlan.objects.create(
    name="V2.8.0 核心全链路回归测试计划",
    description="针对 V2.8.0 新版自愈用例落库和 RAG 二阶段余弦重排的上线，对核心交易下单链路和接口性能发起的全网综合性质量评估。",
    version=version,
    creator=admin,
    is_active=True
)
plan.projects.add(project)
plan.assignees.add(admin)
print("黄金测试计划生成完成")

# 8. 创建已执行测试计划的 TestRun 数据 (报表图表核心数据源)
run = TestRun.objects.create(
    name="V2.8.0 全链路回归 - 自动化与手工联合执行记录",
    description="通过自动化脚本执行与核心链路手工冒烟测试，产出该版本的首轮回归测试报告。",
    test_plan=plan,
    project=project,
    version=version,
    assignee=admin,
    creator=admin,
    status="completed",
    started_at=timezone.now() - timezone.timedelta(hours=2),
    completed_at=timezone.now(),
    due_date=timezone.now() + timezone.timedelta(days=1)
)

# 写入通过、阻塞、失败等各个状态，模拟最真实的分析报表大盘数据
results_choices = [
    {"status": "passed", "actual": "实际执行结果符合预期，账号登入成功，localStorage 保存的 Token 有效。"},
    {"status": "passed", "actual": "购物车加入与数量累加功能验证通过，总价格拆折计算精准无误。"},
    {"status": "passed", "actual": "订单提交后端响应在 80ms 内，顺利创建 PENDING_PAY 订单并跳转收银台。"},
    {"status": "failed", "actual": "报错信息：支付宝签名回调验签失败。由于支付宝公钥环境配置与本地沙箱证书不匹配，抛出 400 异常验证失败。"},
    {"status": "blocked", "actual": "接口在高并发时因为本地模拟 Redis 未拉起，压测接口响应阻塞，无法得出准确 RT 值。"}
]

for idx, tc in enumerate(created_cases):
    res = results_choices[idx]
    TestRunCase.objects.create(
        test_run=run,
        testcase=tc,
        status=res["status"],
        priority=tc.priority,
        actual_result=res["actual"],
        comments="首轮自动化回归测试产出",
        executed_by=admin,
        executed_at=timezone.now() - timezone.timedelta(minutes=30)
    )
print("黄金执行记录及用例结果填充完成")

# 9. 创建高标准评审模板
template = ReviewTemplate.objects.create(
    name="用例设计标准与RAG大模型评审规范",
    description="用于指导 AI 智能评审和人工用例走查的行业标准用例结构评审规范。",
    creator=admin,
    checklist=[
        {"id": "1", "item": "是否明确定义了系统登录态及前置预设数据条件？"},
        {"id": "2", "item": "测试步骤是否完整覆盖了正向操作和逆向异常流程？"},
        {"id": "3", "item": "预期结果是否给出了明确的界面重定向、状态机流转和落库变化？"},
        {"id": "4", "item": "是否针对高频操作（如订单支付、购物车）设置了防重或并发控制？"}
    ],
    is_active=True
)
template.project.add(project)
template.default_reviewers.add(admin)
print("高级评审模板创建完成")

# 10. 创建高水准评审任务及评审进度 (用例评审大盘核心数据源)
review = TestCaseReview.objects.create(
    title="V2.8.0 核心功能全链路 AI & 手工联合评审任务",
    description="对 V2.8.0 基线版本相关的 5 条核心用例发起的高规格评审，检查用例是否符合质量规范标准。",
    creator=admin,
    template=template,
    status="in_progress",
    priority="high",
    deadline=timezone.now() + timezone.timedelta(days=2)
)
review.projects.add(project)
review.testcases.set(created_cases)

# 写入管理员的评审分配，初始状态设为 pending
ReviewAssignment.objects.create(
    review=review,
    reviewer=admin,
    status="pending",
    comment="",
    checklist_results={
        "1": True,
        "2": True
    }
)
print("用例评审任务分配创建完成")

print("\n演示数据种子注入成功！您可以直接对外展示该平台了！")
