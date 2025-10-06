"""
Test script để kiểm tra agent integration
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_agent_import():
    """Test if agent can be imported successfully"""
    try:
        from app.agent import agent, root_agent
        print("✅ Agent import successful!")
        print(f"Agent name: {root_agent.name}")
        print(f"Agent model: {root_agent.model}")
        print(f"Number of tools: {len(root_agent.tools)}")
        print("Tools:")
        for i, tool in enumerate(root_agent.tools, 1):
            print(f"  {i}. {tool.name if hasattr(tool, 'name') else type(tool).__name__}")
        return True
    except Exception as e:
        print(f"❌ Agent import failed: {e}")
        return False

def test_tools_import():
    """Test if tools can be imported successfully"""
    try:
        from app.tools.search import search_products
        from app.tools.explore import explore_product
        from app.tools.compare import compare_products
        from app.tools.memory_tools import memorize, memorize_list, get_memory, store_search_memory
        print("✅ Tools import successful!")
        return True
    except Exception as e:
        print(f"❌ Tools import failed: {e}")
        return False

def test_agent_creation():
    """Test if agent can be created successfully"""
    try:
        from app.optimized_memory_agent import OptimizedMemoryAgent
        from app.shared_libraries.constants import MODEL_GEMINI_2_5_FLASH_LITE
        
        agent = OptimizedMemoryAgent(
            model=MODEL_GEMINI_2_5_FLASH_LITE,
            name="test_agent",
            instruction="Test instruction",
            tools=[]
        )
        print("✅ Agent creation successful!")
        return True
    except Exception as e:
        print(f"❌ Agent creation failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Testing Agent Integration")
    print("=" * 40)
    
    tests = [
        ("Tools Import", test_tools_import),
        ("Agent Creation", test_agent_creation),
        ("Agent Import", test_agent_import),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Testing {test_name}...")
        if test_func():
            passed += 1
        else:
            print(f"❌ {test_name} failed")
    
    print(f"\n📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Agent is ready for ADK web.")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")

if __name__ == "__main__":
    main()
