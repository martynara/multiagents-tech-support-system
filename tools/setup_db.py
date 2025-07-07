import asyncio
import sys
from pathlib import Path
import psycopg
import platform

if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from langgraph.checkpoint.postgres import PostgresSaver
    print("LangGraph PostgresSaver imported successfully")
except ImportError as e:
    print(f"Failed to import PostgresSaver: {e}")
    print("Install with: pip install langgraph-checkpoint-postgres")
    sys.exit(1)

try:
    from support_system.config import settings
    print(f"Config imported successfully")
    print(f"Database URL: {settings.database_url}")
except ImportError as e:
    print(f"Failed to import config: {e}")
    print("Using fallback database URL")
    class FallbackSettings:
        database_url = "postgresql://postgres:example@localhost:5433/postgres?sslmode=disable"
    settings = FallbackSettings()

async def setup_database():
    print("Setting up PostgreSQL database for LangGraph...")
    print("=" * 60)
    
    try:
        print("Testing connection...")
        conn = await psycopg.AsyncConnection.connect(settings.database_url)
        await conn.close()
        print("Connection successful!")
        
        print("Setting up LangGraph tables...")
        
        with PostgresSaver.from_conn_string(settings.database_url) as checkpointer:
            checkpointer.setup()
        
        print("LangGraph checkpoint tables created successfully!")
        
        print("Verifying tables...")
        conn = await psycopg.AsyncConnection.connect(settings.database_url)
        async with conn.cursor() as cur:
            await cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;")
            tables = await cur.fetchall()
            
            print("Database tables:")
            for table in tables:
                print(f"   {table[0]}")
            
            await conn.close()
        
        print("\nSetup complete!")
        print("Adminer: http://localhost:8080")
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    asyncio.run(setup_database())