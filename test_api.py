"""Quick test of the Omninet API."""
import asyncio

import httpx


async def test_register():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "http://localhost:8000/api/v1/auth/register",
                json={
                    "nickname": "testuser",
                    "email": "test@example.com",
                    "password": "test123456"
                }
            )
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_register())
