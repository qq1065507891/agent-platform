-- 初始化管理员账号（PostgreSQL）
-- 可根据需要修改 username/email/password

DELETE FROM users WHERE email = 'admin@example.com';

INSERT INTO users (id, username, email, password_hash, role, status, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'admin',
    'admin@example.com',
    'e66860546f18cdbbcd86b35e18b525bffc67f772c650cedfe3ff7a0026fa1dee',
    'admin',
    'active',
    NOW(),
    NOW()
);

-- 默认密码：Passw0rd!（SHA256）
