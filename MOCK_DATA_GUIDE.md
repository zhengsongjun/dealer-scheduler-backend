# Mock Data 生成指南

## 概述

`mock_data.py` 用于生成测试数据并插入到 PostgreSQL 数据库中，支持 dealer-manager 项目的开发和测试。

## 前置条件

1. PostgreSQL 数据库已启动并运行
2. 数据库连接配置正确（默认：`postgresql://postgres:123456@localhost:5432/dealer_manager`）
3. 已运行 Alembic 迁移，数据库表结构已创建
4. 员工数据文件存在：`backend/600_employer.json`

## 快速使用

```bash
cd backend
python mock_data.py
```

## 数据生成规则

### 1. Dealers（员工表）

**数据来源：** `600_employer.json`

**生成规则：**
- 数量：600 条
- `id`: 自动生成 `100001` - `100600`
- `ee_number`: 从 JSON 的 `eenumber` 字段映射
- `first_name` / `last_name`: 从 JSON 映射
- `type`: 全部 `"tournament"`
- `employment`: 全部 `"full_time"`
- `preferred_shift`: 75% `"day"`, 25% `"swing"`
- `days_off`: 随机 2 天休息日（0-6 数组）
- `seniority_date`: 随机过去 1-10 年的日期
- `phone`: 随机生成 `702-555-xxxx`
- `is_active`: `true`

### 2. Availability Requests（可用性提交）

**生成规则：**
- 数量：600 条（每个 dealer 一条）
- `dealer_id`: 关联 dealers.id
- `week_start`: **固定为周五**（如 `2026-05-29`）
- `shift`: 75% `"day"`, 25% `"swing"`
- `preferred_days_off`: 随机 1-2 天（0-6 数组）
- `submitted_at`: week_start 前 1-7 天内随机时间

**重要：** `week_start` 必须是周五，因为系统使用 Fri-Thu 周制。

### 3. Time Off Requests（请假申请）

**生成规则：**
- 数量：20 条
- 随机选择 20 个 dealer
- `start_date` = `end_date`（单天请假）
- 日期分布：
  - 75%（15 人）请假在工作日（周一到周五）
  - 25%（5 人）请假在周末（周六周日）
- `reason`: 随机选择 `["personal", "family", "medical", "appointment", "travel"]`
- `status`: `"pending"`
- `submitted_at`: 请假日期前 1-10 天随机时间

### 4. Carpool Groups & Members（车队）

**生成规则：**
- 成员数：12 人（600 的 2%）
- 车队数：3-4 个组
- 每组：3-4 个成员
- 第一个成员为司机（`is_driver = true`）
- `group_id`: `CP001`, `CP002`, `CP003`...

## 修改指南

### 修改周期时间

找到脚本中的这两行：

```python
WEEK_START = date(2026, 5, 29)  # Friday
WEEK_END = date(2026, 6, 4)     # Thursday
```

**注意：** `WEEK_START` 必须是周五，使用以下 Python 代码计算：

```python
from datetime import date, timedelta

def get_friday(year, month, day):
    d = date(year, month, day)
    weekday = d.weekday()  # 0=Mon, 4=Fri, 6=Sun
    if weekday < 4:
        # 往前找上周五
        offset = weekday + 3
        return d - timedelta(days=offset)
    elif weekday == 4:
        # 已经是周五
        return d
    else:
        # 周末，往前找本周五
        offset = weekday - 4
        return d - timedelta(days=offset)

# 示例：如果你想要包含 5/26 的那一周
print(get_friday(2026, 5, 26))  # 输出: 2026-05-22 (上周五)
# 或者
print(get_friday(2026, 5, 29))  # 输出: 2026-05-29 (本周五)
```

### 修改数据比例

**Shift 分布（day/swing）：**

```python
day_shift_count = int(len(employees) * 0.75)  # 改这里的 0.75
```

**请假人数和分布：**

```python
chosen = random.sample(dealer_ids, 20)  # 改这里的 20

# 工作日/周末比例
if i < 15:  # 改这里的 15（75% of 20）
    leave_date = random.choice(weekdays)
else:
    leave_date = random.choice(weekends)
```

**车队人数和组数：**

```python
chosen = random.sample(dealer_ids, 12)  # 改这里的 12（2% of 600）
num_groups = random.choice([3, 4])      # 改这里的组数范围
```

### 修改数据库连接

```python
DB_URL = "postgresql://postgres:123456@localhost:5432/dealer_manager"
```

或者使用环境变量：

```python
import os
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:123456@localhost:5432/dealer_manager")
```

### 更换员工数据源

如果要使用不同的 JSON 文件（如 `500_employer.json`）：

```python
with open("500_employer.json", "r") as f:  # 改文件名
    employees = json.load(f)
```

确保 JSON 格式为：

```json
[
  {
    "lastname": "Smith",
    "firstname": "John",
    "eenumber": "800123456"
  }
]
```

## 数据清理

脚本会自动清空以下表的所有数据：

```python
DELETE FROM carpool_members
DELETE FROM carpool_groups
DELETE FROM schedule_entries
DELETE FROM schedules
DELETE FROM availability_requests
DELETE FROM time_off_requests
DELETE FROM ride_share_requests
DELETE FROM dealers
```

**警告：** 运行脚本会删除所有现有数据，请确保已备份重要数据。

## 验证数据

运行脚本后，检查输出：

```
Clearing database...
Done! Inserted:
  dealers:               600
  availability_requests: 600
  time_off_requests:     20
  carpool_groups:        3
  carpool_members:       12
```

### 在 Admin 端验证

1. 启动 backend：`uvicorn app.main:app --reload --port 8000`
2. 启动 admin 前端
3. 进入 Requests 页面
4. 选择对应的周（如 5/29 那一周）
5. 应该能看到 600 条 availability 数据

### SQL 验证

```sql
-- 检查 dealers 数量
SELECT COUNT(*) FROM dealers;

-- 检查 availability 的 week_start
SELECT week_start, COUNT(*) FROM availability_requests GROUP BY week_start;

-- 检查 shift 分布
SELECT shift, COUNT(*) FROM availability_requests GROUP BY shift;

-- 检查请假日期分布
SELECT start_date, COUNT(*) FROM time_off_requests GROUP BY start_date ORDER BY start_date;

-- 检查车队
SELECT g.name, COUNT(m.dealer_id) as members
FROM carpool_groups g
LEFT JOIN carpool_members m ON g.id = m.group_id
GROUP BY g.id, g.name;
```

## 常见问题

### Q: Admin 端看不到数据？

**A:** 检查以下几点：
1. `week_start` 是否是周五
2. Admin 选择的周是否和数据库中的 `week_start` 匹配
3. Backend API 是否正常运行（访问 `http://localhost:8000/health`）
4. 浏览器控制台是否有 API 错误

### Q: 如何生成多周数据？

**A:** 修改脚本，循环生成多个 `week_start`：

```python
weeks = [
    date(2026, 5, 22),  # Week 1
    date(2026, 5, 29),  # Week 2
    date(2026, 6, 5),   # Week 3
]

for week in weeks:
    for dealer_id in dealer_ids:
        # 生成 availability_request
        ...
```

### Q: 如何保留现有数据？

**A:** 注释掉清理数据的部分：

```python
# with engine.begin() as conn:
#     conn.execute(text("DELETE FROM ..."))
```

但要注意可能的主键冲突。

## 相关文件

- `mock_data.py` - 数据生成脚本
- `600_employer.json` - 员工数据源
- `app/models/*.py` - 数据库模型定义
- `alembic/versions/*.py` - 数据库迁移文件

## 更新日志

- 2026-04-01: 初始版本，支持 600 人数据生成
