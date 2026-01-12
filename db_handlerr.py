import os
import logging
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import DictCursor
from typing import Optional, Dict, List, Any
from datetime import datetime

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class DatabaseHandler:
    def __init__(self):
        self.pool = None
        self.db_config = {
            'dbname': os.getenv('DB_NAME', 'postgres'),
            'user': os.getenv('DB_USER'),
            'password': os.getenv('DB_PASSWORD'),
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', '5432'))
        }
        self._init_pool()

    def _init_pool(self) -> bool:
        """Initialize database connection pool"""
        try:
            if not all([self.db_config['user'], self.db_config['password'], self.db_config['host']]):
                logger.error("Missing database configuration")
                return False

            self.pool = SimpleConnectionPool(
                1, 20,
                **self.db_config,
                connect_timeout=30,
                keepalives=1,
                keepalives_idle=30
            )
            return True
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            return False

    def get_connection(self):
        """Get a connection from the pool"""
        if not self.pool:
            if not self._init_pool():
                return None
        return self.pool.getconn()

    def return_connection(self, conn):
        """Return a connection to the pool"""
        if self.pool and conn:
            self.pool.putconn(conn)

    def check_connection(self) -> bool:
        """Test database connection"""
        conn = self.get_connection()
        if not conn:
            return False
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT 1')
                return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
        finally:
            self.return_connection(conn)

    def execute_query(self, query: str, params: tuple = None, fetch: bool = False):
        """Execute a database query with proper error handling"""
        conn = self.get_connection()
        if not conn:
            return None

        try:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute(query, params)
                if fetch:
                    result = cur.fetchall()
                else:
                    result = None
                conn.commit()
                return result
        except Exception as e:
            logger.error(f"Query execution error: {e}")
            conn.rollback()
            return None
        finally:
            self.return_connection(conn)

    # Add more methods as needed for database operations