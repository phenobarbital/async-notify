#!/usr/bin/env python3
"""
Test script to validate async-notify installation and core functionality.
"""
import os
import sys
import asyncio
from pathlib import Path

# Create required directories
env_dir = Path(__file__).parent.parent / "env"
env_dir.mkdir(exist_ok=True)

# Set minimal environment variables
os.environ["DEBUG"] = "True"
os.environ["ENV"] = "development"
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6379"
os.environ["NOTIFY_DB"] = "5"
os.environ["NOTIFY_DEFAULT_HOST"] = "127.0.0.1"
os.environ["NOTIFY_DEFAULT_PORT"] = "8991"
os.environ["TEMPLATE_DIR"] = str(Path(__file__).parent.parent / "templates")

# Import version first
from notify.version import __version__

# Now import notify components
from notify import Notify
from notify.server import NotifyWorker, NotifyClient
from notify.models import Actor, Account

async def test_dummy():
    """Test dummy provider."""
    print("Testing dummy provider...")
    try:
        dummy = Notify("dummy")
        await dummy.send(
            recipient=["test@example.com"],
            subject="Test",
            message="Hello from async-notify!"
        )
        print("✓ Dummy provider test passed")
        return True
    except Exception as e:
        print(f"✗ Dummy provider test failed: {e}")
        print(f"Error details: {str(e)}")
        return False

async def test_server():
    """Test server components."""
    print("Testing server components...")
    try:
        # Start worker
        worker = NotifyWorker(
            host="127.0.0.1",
            port=8991,
            debug=True
        )
        worker_task = asyncio.create_task(worker.start())
        
        # Give worker time to start
        await asyncio.sleep(2)
        
        # Create client
        client = NotifyClient(
            tcp_host="127.0.0.1",
            tcp_port=8991
        )
        
        # Send test message
        await client.send({
            "provider": "dummy",
            "recipient": ["test@example.com"],
            "message": "Test message"
        })
        
        # Clean up
        await worker.stop()
        await worker_task
        print("✓ Server components test passed")
        return True
    except Exception as e:
        print(f"✗ Server components test failed: {e}")
        print(f"Error details: {str(e)}")
        return False

async def test_models():
    """Test data models."""
    print("Testing data models...")
    try:
        actor = Actor(
            name="Test User",
            account=Account(
                provider="dummy",
                address="test@example.com"
            )
        )
        assert actor.name == "Test User"
        assert actor.account.provider == "dummy"
        print("✓ Data models test passed")
        return True
    except Exception as e:
        print(f"✗ Data models test failed: {e}")
        print(f"Error details: {str(e)}")
        return False

async def main():
    """Run all tests."""
    print("\nTesting async-notify installation...\n")
    
    # Print version info
    print(f"Python version: {sys.version.split()[0]}")
    print(f"async-notify version: {__version__}\n")
    
    # Run tests
    try:
        results = await asyncio.gather(
            test_dummy(),
            test_server(),
            test_models(),
            return_exceptions=True
        )
        
        # Filter out exceptions and print them
        results = [
            result if not isinstance(result, Exception) else False 
            for result in results
        ]
        
        # Print summary
        print("\nTest Summary:")
        print("------------")
        total = len(results)
        passed = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False)
        print(f"Total tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        
        if failed == 0:
            print("\n✓ All tests passed - Installation is working correctly!")
            return 0
        else:
            print("\n✗ Some tests failed - Check the output above for details")
            return 1
            
    except Exception as e:
        print(f"\nError running tests: {e}")
        print(f"Error details: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))