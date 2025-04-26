"""
Cache module for the application.
This module contains the cache instance that can be imported by any module
without creating circular imports.
"""
from flask_caching import Cache

# Initialize cache without app
cache = Cache()
