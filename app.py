import streamlit as st
import sqlite3
import random
import pandas as pd

# Подключаем базу данных
DB_NAME = "port_control_combined.db"

st.set_page_config(page_title="Умный Светофор Порта", page_icon="⚓", layout="wide")


# ==========================================
# АВТОПРОВЕРКА И ОБНОВЛЕНИЕ СТРУКТУРЫ БД
# ==========================================
def upgrade_and_init_db():
    """Создает или обновляет таблицы базы данных под новую структуру."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Создаем таблицу ресурсов, если её нет
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resources (
            name TEXT PRIMARY KEY,
            total_count INTEGER,
            available_count INTEGER
        )
    """)

    # Пересоздаем таблицу причалов с новой колонкой current_ship
    cursor.execute("DROP TABLE IF EXISTS berths")
    cursor.execute("""
        CREATE TABLE berths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            max_length REAL,
            max_draft REAL,
            cargo_type TEXT,
            status TEXT DEFAULT 'свободен',
            current_ship TEXT DEFAULT '-'
        )
    """)

    # ИСПРАВЛЕНО: Явно указываем колонки, куда вставляем 6 значений (id пропустится автоматически)
    berths = [
        ("Причал №1 (Малый/Зерно)", 150.0, 8.0, "зерно", "свободен", "-"),
        ("Причал №2 (Средний/Контейнеры)", 220.0, 11.5, "контейнеры", "свободен", "-"),
        ("Причал №3 (Большой/Нефть)", 310.0, 15.0, "нефть", "свободен", "-")
    ]
    cursor.executemany("""
        INSERT INTO berths (name, max_length, max_draft, cargo_type, status, current_ship) 
        VALUES (?, ?, ?, ?, ?, ?)
    """, berths)

    cursor.execute("INSERT OR REPLACE INTO resources VALUES ('буксиры', 3, 3)")
    conn.commit()
    conn.close()


# Запускаем инициализацию при первом старте, чтобы добавить новую колонку
if 'db_initialized' not in st.session_state:
    upgrade_and_init_db()
    st.session_state.db_initialized = True

st.title("⚓ Автоматизированная система 'Светофор Порта'")
st.subheader("Система мониторинга причалов и швартовки")

# ==========================================
# ИМИТАЦИЯ ПОГОДЫ
# ==========================================
if 'wind_speed' not in st.session_state:
    st.session_state.wind_speed = round(random.uniform(2.0, 25.0), 1)

wind = st.session_state.wind_speed
is_storm = wind > 18.0

st.sidebar.header("Метеоусловия в порту")
if is_storm:
    st.sidebar.error(f"🔴 ШТОРМ! Ветер: {wind} м/с")
    st.sidebar.warning("Внимание: Швартовка временно запрещена!")
else:
    st.sidebar.success(f"🟢 ПОГОДА НОРМА. Ветер: {wind} м/с")

# Кнопка для ручного сброса базы данных
if st.sidebar.button("Очистить причалы (Сброс порта)"):
    upgrade_and_init_db()
    st.sidebar.info("Порт полностью освобожден.")

# ==========================================
# МОНИТОРИНГ ПОРТА В РЕАЛЬНОМ ВРЕМЕНИ
# ==========================================
st.markdown("### 📊 Мониторинг порта в реальном времени")
col_left, col_right = st.columns(2)

conn = sqlite3.connect(DB_NAME)
# Теперь выгружаем и колонку 'Текущее судно'
df_berths = pd.read_sql_query("""
    SELECT id, name as 'Название причала', max_length as 'Макс. длина', 
    max_draft as 'Макс. осадка', cargo_type as 'Тип груза', 
    status as 'Статус', current_ship as 'Текущее судно' 
    FROM berths
""", conn)

cursor = conn.cursor()
cursor.execute("SELECT available_count, total_count FROM resources WHERE name = 'буксиры'")
tugs_data = cursor.fetchone()
conn.close()

with col_left:
    st.write("**Состояние причалов:**")
    st.dataframe(df_berths, use_container_width=True, hide_index=True)

with col_right:
    st.write("**Доступные ресурсы:**")
    if tugs_data:
        st.metric(label="Свободные буксиры", value=f"{tugs_data[0]} из {tugs_data[1]}")

st.markdown("---")

# ==========================================
# ИНТЕРФЕЙС: ДВЕ КОЛОНКИ
# ==========================================
col_form, col_dispatcher = st.columns(2)

with col_form:
    with st.form("ship_form"):
        st.markdown("### 📥 Отправить запрос на заход:")

        ship_name = st.text_input("Название корабля", placeholder="Например, Омега")
        ship_length = st.number_input("Физическая длина корабля (в метрах)", min_value=10.0, max_value=500.0,
                                      value=150.0)
        ship_draft = st.number_input("Текущая осадка корабля (глубина в метрах)", min_value=1.0, max_value=25.0,
                                     value=8.0)
        ship_cargo = st.selectbox("Тип перевозимого груза", ["зерно", "контейнеры", "нефть"])
        submitted = st.form_submit_button("Запросить разрешение на вход")

with col_dispatcher:
    st.markdown("### 📤 Диспетчерская: Управление уходом судов")
    st.write("Выберите причал, чтобы отправить разгруженный корабль обратно в море.")

    # Получаем из базы список причалов, которые сейчас ЗАНЯТЫ
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, current_ship FROM berths WHERE status = 'занят'")
    occupied_berths = cursor.fetchall()
    conn.close()

    if not occupied_berths:
        st.info("В порту пока нет занятых причалов.")
    else:
        # Формируем красивый список, где видно и причал, и имя корабля на нем
        berth_options = {f"{b[1]} (Корабль: {b[2]})": b[0] for b in occupied_berths}
        selected_berth_label = st.selectbox("Выберите причал для освобождения:", list(berth_options.keys()))

        if st.button("Освободить причал и отправить судно в рейс"):
            berth_id_to_free = berth_options[selected_berth_label]

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            # Сбрасываем статус причала и очищаем имя корабля (ставим прочерк '-')
            cursor.execute("UPDATE berths SET status = 'свободен', current_ship = '-' WHERE id = ?",
                           (berth_id_to_free,))
            cursor.execute(
                "UPDATE resources SET available_count = MIN(available_count + 1, total_count) WHERE name = 'буксиры'")

            conn.commit()
            conn.close()

            st.success("Причал успешно освобожден, корабль ушел в море!")
            st.rerun()

# ==========================================
# ЛОГИКА ОБРАБОТКИ СВЕТОФОРА
# ==========================================
if submitted:
    if not ship_name:
        st.warning("Пожалуйста, введите название корабля!")
    else:
        if is_storm:
            st.error(f"🔴 СИГНАЛ КРАСНЫЙ для '{ship_name}'!")
            st.info(
                "ℹ️ КОМАНДА: В порту объявлено штормовое предупреждение. Следуйте в зону ожидания и **ЗАГЛУШИТЕ ДВИГАТЕЛЬ**.")
        else:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, name FROM berths 
                WHERE status = 'свободен' 
                  AND max_length >= ? 
                  AND max_draft >= ? 
                  AND cargo_type = ?
            """, (ship_length, ship_draft, ship_cargo))

            berth = cursor.fetchone()

            if not berth:
                st.error(f"🔴 СИГНАЛ КРАСНЫЙ для '{ship_name}'!")
                st.info(
                    "ℹ️ КОМАНДА: Нет свободных причалов под ваши габариты или тип груза. Следуйте на рейд и **ЗАГЛУШИТЕ ДВИГАТЕЛЬ**.")
                conn.close()
            else:
                berth_id, berth_name = berth

                cursor.execute("SELECT available_count FROM resources WHERE name = 'буксиры'")
                tugs_available = cursor.fetchone()

                if tugs_available[0] < 1:
                    st.warning(f"🟡 СИГНАЛ ЖЕЛТЫЙ для '{ship_name}'!")
                    st.info(
                        "ℹ️ КОМАНДА: Причал готов, но все буксиры заняты. Ожидайте на внешнем рейде, снизьте обороты двигателя.")
                    conn.close()
                else:
                    # ЗАПИСЫВАЕМ ИМЯ КОРАБЛЯ В БАЗУ ДАННЫХ ПРИ СВЯЗКЕ С ПРИЧАЛОМ
                    cursor.execute("UPDATE berths SET status = 'занят', current_ship = ? WHERE id = ?",
                                   (ship_name, berth_id))
                    cursor.execute("UPDATE resources SET available_count = available_count - 1 WHERE name = 'буксиры'")
                    conn.commit()
                    conn.close()

                    st.success(f"🟢 СИГНАЛ ЗЕЛЕНЫЙ для '{ship_name}'!")
                    st.balloons()
                    st.write(
                        f"**Инструкция капитану:** Заходите в гавань. Направляйтесь к **{berth_name}**. Вам выделен буксир сопровождения.")
                    st.rerun()
