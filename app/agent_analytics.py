"""
Agent Analytics và Token Counting Utilities
Phân tích logs và tính toán thống kê về agent performance
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, Counter
import statistics

logger = logging.getLogger(__name__)

class AgentAnalytics:
    """Phân tích và thống kê agent performance từ logs"""
    
    def __init__(self, log_file: str = "agent_interactions.log"):
        self.log_file = log_file
        self.sessions = defaultdict(list)
        self.tool_usage = defaultdict(list)
        self.token_stats = defaultdict(list)
        
    def parse_logs(self, hours_back: int = 24) -> Dict[str, Any]:
        """Parse logs từ file và trích xuất thống kê"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if "AGENT_INTERACTION:" in line:
                        try:
                            # Extract JSON from log line
                            json_start = line.find('{')
                            if json_start != -1:
                                log_data = json.loads(line[json_start:])
                                self._process_log_entry(log_data, cutoff_time)
                        except json.JSONDecodeError:
                            continue
                            
            return self._generate_analytics()
            
        except FileNotFoundError:
            logger.warning(f"Log file {self.log_file} not found")
            return {"error": "Log file not found"}
        except Exception as e:
            logger.error(f"Error parsing logs: {e}")
            return {"error": str(e)}
    
    def _process_log_entry(self, log_data: Dict[str, Any], cutoff_time: datetime):
        """Process individual log entry"""
        try:
            timestamp = datetime.fromtimestamp(log_data.get('timestamp', 0))
            if timestamp < cutoff_time:
                return
                
            interaction_type = log_data.get('type', '')
            data = log_data.get('data', {})
            tokens = log_data.get('tokens', 0)
            
            # Group by session
            session_id = data.get('session_id', 'unknown')
            self.sessions[session_id].append(log_data)
            
            # Track token usage
            if tokens > 0:
                self.token_stats[interaction_type].append(tokens)
                
        except Exception as e:
            logger.warning(f"Error processing log entry: {e}")
    
    def _generate_analytics(self) -> Dict[str, Any]:
        """Generate comprehensive analytics"""
        analytics = {
            "summary": self._get_summary_stats(),
            "token_analysis": self._get_token_analysis(),
            "session_analysis": self._get_session_analysis(),
            "performance_metrics": self._get_performance_metrics(),
            "tool_usage": self._get_tool_usage_stats()
        }
        return analytics
    
    def _get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics"""
        total_sessions = len(self.sessions)
        total_interactions = sum(len(session) for session in self.sessions.values())
        
        # Count interaction types
        interaction_counts = Counter()
        for session in self.sessions.values():
            for entry in session:
                interaction_counts[entry.get('type', 'unknown')] += 1
        
        return {
            "total_sessions": total_sessions,
            "total_interactions": total_interactions,
            "interaction_types": dict(interaction_counts),
            "avg_interactions_per_session": total_interactions / total_sessions if total_sessions > 0 else 0
        }
    
    def _get_token_analysis(self) -> Dict[str, Any]:
        """Analyze token usage patterns"""
        token_analysis = {}
        
        # Separate input and output tokens
        input_tokens = []
        output_tokens = []
        
        for interaction_type, tokens in self.token_stats.items():
            if tokens:
                token_analysis[interaction_type] = {
                    "count": len(tokens),
                    "total_tokens": sum(tokens),
                    "avg_tokens": statistics.mean(tokens),
                    "min_tokens": min(tokens),
                    "max_tokens": max(tokens),
                    "median_tokens": statistics.median(tokens)
                }
                
                # Categorize tokens by type
                if interaction_type in ["INPUT_RECEIVED", "PROMPT_ENHANCED"]:
                    input_tokens.extend(tokens)
                elif interaction_type in ["LLM_RESPONSE"]:
                    output_tokens.extend(tokens)
        
        # Calculate total token usage with actual input/output split
        all_tokens = [token for tokens in self.token_stats.values() for token in tokens]
        if all_tokens:
            token_analysis["overall"] = {
                "total_tokens": sum(all_tokens),
                "input_tokens": sum(input_tokens),
                "output_tokens": sum(output_tokens),
                "input_output_ratio": {
                    "input_percentage": (sum(input_tokens) / sum(all_tokens) * 100) if all_tokens else 0,
                    "output_percentage": (sum(output_tokens) / sum(all_tokens) * 100) if all_tokens else 0
                },
                "avg_tokens_per_interaction": statistics.mean(all_tokens),
                "total_interactions": len(all_tokens)
            }
        
        return token_analysis
    
    def _get_session_analysis(self) -> Dict[str, Any]:
        """Analyze session patterns"""
        session_lengths = [len(session) for session in self.sessions.values()]
        session_durations = []
        
        for session_id, session in self.sessions.items():
            if len(session) > 1:
                start_time = min(entry.get('timestamp', 0) for entry in session)
                end_time = max(entry.get('timestamp', 0) for entry in session)
                duration = end_time - start_time
                session_durations.append(duration)
        
        return {
            "total_sessions": len(self.sessions),
            "avg_session_length": statistics.mean(session_lengths) if session_lengths else 0,
            "max_session_length": max(session_lengths) if session_lengths else 0,
            "avg_session_duration": statistics.mean(session_durations) if session_durations else 0,
            "max_session_duration": max(session_durations) if session_durations else 0
        }
    
    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics from logs"""
        performance_data = defaultdict(list)
        
        for session in self.sessions.values():
            for entry in session:
                data = entry.get('data', {})
                if 'total_processing_time' in data:
                    performance_data['total_time'].append(data['total_processing_time'])
                if 'llm_processing_time' in data:
                    performance_data['llm_time'].append(data['llm_processing_time'])
                if 'memory_search_time' in data:
                    performance_data['memory_time'].append(data['memory_search_time'])
        
        metrics = {}
        for metric, values in performance_data.items():
            if values:
                metrics[metric] = {
                    "avg": statistics.mean(values),
                    "min": min(values),
                    "max": max(values),
                    "median": statistics.median(values),
                    "count": len(values)
                }
        
        return metrics
    
    def _get_tool_usage_stats(self) -> Dict[str, Any]:
        """Get tool usage statistics"""
        # This would need to be populated from tool logs
        # For now, return placeholder
        return {
            "note": "Tool usage stats require separate tool log parsing"
        }
    
    def print_analytics_report(self, hours_back: int = 24):
        """Print a formatted analytics report"""
        analytics = self.parse_logs(hours_back)
        
        if "error" in analytics:
            print(f"Error: {analytics['error']}")
            return
        
        print("=" * 80)
        print("AGENT ANALYTICS REPORT")
        print("=" * 80)
        print(f"Time Period: Last {hours_back} hours")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Summary
        summary = analytics["summary"]
        print("📊 SUMMARY STATISTICS")
        print("-" * 40)
        print(f"Total Sessions: {summary['total_sessions']}")
        print(f"Total Interactions: {summary['total_interactions']}")
        print(f"Avg Interactions/Session: {summary['avg_interactions_per_session']:.2f}")
        print()
        
        # Token Analysis
        token_analysis = analytics["token_analysis"]
        if token_analysis:
            print("🔢 TOKEN USAGE ANALYSIS")
            print("-" * 40)
            
            if "overall" in token_analysis:
                overall = token_analysis["overall"]
                print(f"Total Tokens Used: {overall['total_tokens']:,}")
                print(f"  Input Tokens: {overall['input_tokens']:,} ({overall['input_output_ratio']['input_percentage']:.1f}%)")
                print(f"  Output Tokens: {overall['output_tokens']:,} ({overall['input_output_ratio']['output_percentage']:.1f}%)")
                print(f"Avg Tokens/Interaction: {overall['avg_tokens_per_interaction']:.1f}")
                print(f"Total Interactions: {overall['total_interactions']}")
                print()
            
            for interaction_type, stats in token_analysis.items():
                if interaction_type != "overall":
                    print(f"{interaction_type}:")
                    print(f"  Count: {stats['count']}")
                    print(f"  Total Tokens: {stats['total_tokens']:,}")
                    print(f"  Avg Tokens: {stats['avg_tokens']:.1f}")
                    print(f"  Min/Max: {stats['min_tokens']}/{stats['max_tokens']}")
                    print()
        
        # Performance Metrics
        performance = analytics["performance_metrics"]
        if performance:
            print("⚡ PERFORMANCE METRICS")
            print("-" * 40)
            for metric, stats in performance.items():
                print(f"{metric.replace('_', ' ').title()}:")
                print(f"  Avg: {stats['avg']:.3f}s")
                print(f"  Min/Max: {stats['min']:.3f}s / {stats['max']:.3f}s")
                print(f"  Median: {stats['median']:.3f}s")
                print()
        
        # Session Analysis
        session_analysis = analytics["session_analysis"]
        print("👥 SESSION ANALYSIS")
        print("-" * 40)
        print(f"Total Sessions: {session_analysis['total_sessions']}")
        print(f"Avg Session Length: {session_analysis['avg_session_length']:.1f} interactions")
        print(f"Max Session Length: {session_analysis['max_session_length']} interactions")
        if session_analysis['avg_session_duration'] > 0:
            print(f"Avg Session Duration: {session_analysis['avg_session_duration']:.1f} seconds")
            print(f"Max Session Duration: {session_analysis['max_session_duration']:.1f} seconds")
        print()
        
        print("=" * 80)

def estimate_cost(input_tokens: int, output_tokens: int = 0, model: str = "gemini-2.5-flash-lite") -> Dict[str, float]:
    """Estimate cost based on actual input/output token usage"""
    # Approximate pricing (as of 2024, may need updates)
    pricing = {
        "gemini-2.5-flash-lite": {
            "input": 0.000075,  # per 1K tokens
            "output": 0.0003    # per 1K tokens
        },
        "gemini-2.5-flash": {
            "input": 0.000075,
            "output": 0.0003
        }
    }
    
    if model not in pricing:
        return {"error": f"Pricing not available for model: {model}"}
    
    # Use actual token counts
    input_cost = (input_tokens / 1000) * pricing[model]["input"]
    output_cost = (output_tokens / 1000) * pricing[model]["output"]
    total_cost = input_cost + output_cost
    total_tokens = input_tokens + output_tokens
    
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "input_cost_usd": input_cost,
        "output_cost_usd": output_cost,
        "total_cost_usd": total_cost,
        "input_percentage": (input_tokens / total_tokens * 100) if total_tokens > 0 else 0,
        "output_percentage": (output_tokens / total_tokens * 100) if total_tokens > 0 else 0,
        "model": model
    }

def estimate_cost_from_analytics(analytics_data: Dict[str, Any], model: str = "gemini-2.5-flash-lite") -> Dict[str, float]:
    """Estimate cost from analytics data with actual token counts"""
    token_analysis = analytics_data.get("token_analysis", {})
    overall = token_analysis.get("overall", {})
    
    input_tokens = overall.get("input_tokens", 0)
    output_tokens = overall.get("output_tokens", 0)
    
    return estimate_cost(input_tokens, output_tokens, model)

if __name__ == "__main__":
    # Example usage
    analytics = AgentAnalytics()
    analytics.print_analytics_report(hours_back=24)
    
    # Example cost estimation
    total_tokens = 10000
    cost_estimate = estimate_cost(total_tokens)
    print(f"\n💰 COST ESTIMATION for {total_tokens:,} tokens:")
    print(f"Total Cost: ${cost_estimate['total_cost_usd']:.4f} USD")
    print(f"Input Cost: ${cost_estimate['input_cost_usd']:.4f} USD")
    print(f"Output Cost: ${cost_estimate['output_cost_usd']:.4f} USD")
