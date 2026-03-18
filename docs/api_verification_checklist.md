# API 验证清单（Swagger / Postman）

> Base URL: http://127.0.0.1:8000/api/v1
> 
> 统一响应：{code:0,message:"ok",data:{...}}

---

## 0. 登录获取 token

**POST /auth/login**

```json
{
  "username": "admin",
  "password": "Passw0rd!",
  "login_type": "password"
}
```

**从响应中拷贝 `data.access_token`**

---

## 1. Swagger 设置认证

Swagger 页面右上角 **Authorize**：

```
Bearer <你的token>
```

---

## 2. 用户模块（管理员）

**GET /users**

Query：`page=1&page_size=20`

---

**POST /users**

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "Passw0rd!",
  "role": "user"
}
```

---

**PUT /users/{id}**

```json
{
  "role": "manager",
  "status": "active"
}
```

---

**POST /users/import**

```json
{
  "users": [
    {"username": "d1", "email": "d1@example.com", "password": "Passw0rd!", "role": "user"},
    {"username": "d2", "email": "d2@example.com", "password": "Passw0rd!", "role": "user"}
  ]
}
```

---

## 3. 智能体模块（登录用户）

**POST /agents**

```json
{
  "name": "日报助手",
  "description": "生成日报",
  "prompt_template": "你是一个日报助手...",
  "skills": [{"skill_id": "text_summary"}],
  "is_public": true
}
```

---

**GET /agents**

Query：`page=1&page_size=20`

---

**GET /agents/{id}**

---

**PUT /agents/{id}**

```json
{
  "description": "生成标准化日报",
  "is_public": false
}
```

---

## 4. 会话模块（登录用户）

**POST /conversations**

```json
{
  "agent_id": "<替换为上面创建的 agent_id>"
}
```

---

**GET /conversations/{id}**

---

**POST /conversations/{id}/messages**

```json
{
  "content": "今天完成了接口联调",
  "attachments": []
}
```

---

## 5. 验证要点

- 每个接口都必须返回 `code=0` 与 `message="ok"`
- 管理员接口（users）用非 admin 登录应返回 403
- `POST /conversations/{id}/messages` 会保存一条 mock 回复并返回 `assistant_message`
