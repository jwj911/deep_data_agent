import asyncio

async def execute_function(func_dict):
    # 获取函数名和参数
    func_name = func_dict.get('name')
    args = func_dict.get('args', {})

    # 获取函数对象
    func = globals().get(func_name)
    if not func:
        raise ValueError(f"Function {func_name} not found")

    # 检查是否是异步函数
    if asyncio.iscoroutinefunction(func):
        # 调用异步函数
        await func(**args)
    else:
        # 调用同步函数
        func(**args)