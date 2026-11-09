-- Таблица сессий
create table sessions (
    id serial primary key,
    status text not null default 'active', -- Тип дефолтного статуса опционален
    -- Хранит данные в формате UTC, но при выводе переводит в текущий часовой пояс
    created_at timestamp with time zone default now() 
);

-- Таблица сообщений в сессиях
create table messages (
    id serial primary key,
    -- Внешний ключ на первичный ключ id таблицы sessions, чтобы проверить, что такая сессия существует
    session_id int not null references sessions(id),
    -- Кто написал сообщение
    role text not null,
    content text not null,
    -- Время ответа в мс
    response_time_ms int,
    -- Какие источники использовала модель
    used_sources text,
    -- Хранит данные в формате UTC, но при выводе переводит в текущий часовой пояс
    created_at timestamp with time zone default now()
);

-- Таблица заявок клиентов/компаний
create table leads (
    id serial primary key,
    -- Внешний ключ на первичный ключ id таблицы sessions, чтобы проверить, что такая сессия существует
    session_id int not null references sessions(id),
    client_name text not null,
    client_phone text not null,
    company_name text not null,
    -- Краткое резюме задачи и подобранных продуктов для пресейл-менеджера
    dialog_summary text,
    -- Хранит данные в формате UTC, но при выводе переводит в текущий часовой пояс
    created_at timestamp with time zone default now()
);