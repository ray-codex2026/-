# 开发与验证记录

日期：2026-10-28。环境：Linux，Python 3.12；模拟API，未发生真实付费请求。

| 阶段 | 实现 | 当阶段执行结果 |
|---|---|---|
| 1 | 项目结构、SQLite、上传、管理、SKU去重 | `tests/test_store.py` 2 passed |
| 2 | 场景编辑适配、本地5图、尺寸与格式导出、事实门槛 | store + images 4 passed |
| 3 | 多模态识别、西班牙语五节文案、持久化 | `tests/test_copy.py` 2 passed |
| 4 | 队列、暂停恢复、失败重试、预算、缓存、审核、ZIP | `tests/test_workflow.py` 4 passed |
| 5 | 假API接口契约、SDK签名、九页空数据/有数据冒烟 | 全套 `python -m pytest -q` **15 passed** |

补充检查：`pip check` 无依赖冲突。已实际启动Streamlit，内部HTTP健康端点和首页均返回200，首页返回HTML；不对用户发布云端预览。

修复：界面测试使用绝对路径以适应Streamlit测试工具；模式、起始步骤和任务在同一SQLite事务入队，避免worker抢先读取；暂停/取消状态在步骤结束时保留；后台worker持续轮询避免新队列遗漏；跨进程锁在退出后释放；NaN/无限尺寸拒绝；场景图片在审核前保存pending缓存，避免审核重试重复生图。

未执行：真实OpenAI付费调用、Windows本机脚本运行、GitHub Actions远端执行、50款真实API负载测试、Mercado Libre实时类目规则核查。Windows CI配置已提供，执行状态不能在本地推断。模拟图片与文案明确标注演示用途。1200场景导出是1024图放大，API实际美元成本需要供应商账单人工核对。

Windows启动反馈修复：启动脚本改为ASCII及CRLF行尾，移除括号命令块，支持py或python命令并保留错误窗口。Linux下检查编码与行尾；尚未在Windows实机验证此修复。
