import os
import sys

# 必须在任何 app 模块导入之前设置，使引擎指向内存 SQLite（PostgreSQL 为部署默认）
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SEED_DEMO"] = "0"

sys.path.insert(0, os.path.dirname(__file__))
