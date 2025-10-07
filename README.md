# MMVN Chatbot v.October

A sophisticated AI-powered shopping assistant for MMVN (Mega Market Vietnam) built with Google ADK (Agent Development Kit).

## 🚀 Features

### Core Capabilities
- **Smart Product Search**: Advanced search with Vietnamese language support
- **Product Comparison**: Compare multiple products side-by-side
- **Memory Integration**: Remembers previous conversations and search history
- **Context Optimization**: Intelligent context trimming for optimal performance
- **Real-time Product Display**: Interactive product cards in the frontend

### Technical Features
- **Google ADK Integration**: Built with Google's Agent Development Kit
- **Antsomi Smart Search API**: Advanced product search capabilities
- **GraphQL Product Details**: Detailed product information via GraphQL
- **Memory Management**: Persistent conversation memory
- **Performance Optimized**: Context trimming and token optimization

## 🏗️ Architecture

### Backend (Python)
- **Agent Core**: `app/agent.py` - Main agent with optimized instructions
- **Search Tools**: `app/tools/search.py` - Product search with Antsomi API
- **Explore Tools**: `app/tools/explore.py` - Product detail exploration
- **Memory Tools**: `app/tools/memory_tools.py` - Conversation memory management
- **Context Optimization**: `app/tools/context_optimized_tools.py` - Performance optimization

### Frontend (React + TypeScript)
- **Chat Interface**: Real-time chat with product display
- **Product Cards**: Interactive product cards with images and prices
- **Session Management**: User session and history management
- **Responsive Design**: Mobile-friendly interface

## 🛠️ Installation

### Prerequisites
- Python 3.11+
- Node.js 18+
- Google ADK installed

### Backend Setup
```bash
# Install Python dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your API keys

# Run the agent
python -m app.agent
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## 📊 Performance Optimizations

### Context Management
- **Token Budget**: 3000 tokens per conversation
- **Context Trimming**: Keeps last 5 invocations
- **Smart Filtering**: Removes non-essential content

### Response Optimization
- **Minimal Product Data**: Essential fields only
- **Relevance Scoring**: Smart product ranking
- **Token Counting**: Real-time token estimation

## 🔧 Configuration

### Agent Configuration
- **Model**: Google Gemini (configurable)
- **Tools**: Search, Explore, Compare, Memory
- **Memory**: Persistent conversation storage
- **Caching**: Static instruction caching

### API Integration
- **Antsomi CDP 365**: Product search API
- **GraphQL**: Product details API
- **Memory API**: Conversation persistence

## 📈 Usage Examples

### Product Search
```
User: "Tìm sữa vinamilk"
Agent: [Searches and returns 10 relevant products]
```

### Product Comparison
```
User: "So sánh sữa tươi và sữa bột"
Agent: [Compares products side-by-side]
```

### Memory Integration
```
User: "Sản phẩm nào tôi đã xem trước đó?"
Agent: [Loads from memory and shows previous products]
```

## 🎯 Key Improvements (October Version)

1. **Performance Optimization**
   - Removed caching overhead
   - Direct agent creation
   - Optimized logging

2. **Enhanced Search**
   - Better Vietnamese language support
   - Improved category mapping
   - Smart keyword generation

3. **Memory Integration**
   - Persistent conversation memory
   - Search history tracking
   - Context-aware responses

4. **Frontend Enhancements**
   - Grouped product display
   - Better mobile responsiveness
   - Improved user experience

## 📝 Development

### Adding New Tools
1. Create tool in `app/tools/`
2. Add to agent in `app/agent.py`
3. Update frontend types if needed

### Memory Management
- Use `memorize()` for important information
- Use `store_search_memory()` for search history
- Use `load_memory()` to retrieve context

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🔗 Links

- [Google ADK Documentation](https://google.github.io/adk-docs/)
- [Antsomi CDP 365 API](https://search.ants.tech)
- [MMVN Website](https://online.mmvietnam.com)

---

**Version**: October 2024  
**Status**: Production Ready  
**Maintainer**: MMVN Development Team