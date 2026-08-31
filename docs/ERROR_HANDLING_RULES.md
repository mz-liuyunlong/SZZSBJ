# 错误处理规则

## 统一错误结构

建议使用：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "用户可理解的错误信息",
    "details": {}
  }
}
```

## 后端规则

AI 不允许写：

```python
try:
    ...
except Exception:
    pass
```

也不允许写：

```python
except:
    return None
```

必须记录上下文，并转换为统一错误结构或安全抛出。

## 前端规则

前端必须处理：

- Loading
- Empty
- Error
- Permission denied
- Retry when applicable

不允许接口失败后静默无提示。
