"""Pytest configuration — adds the project root to sys.path."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
