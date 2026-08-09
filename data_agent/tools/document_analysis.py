import os
from typing import Optional


def analyze_document(file_path: str) -> dict:
    """Analyze a document and return its content and metadata"""
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Read file content (limit to 10000 characters)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(10000)
        
        # Get file extension
        file_extension = os.path.splitext(file_path)[1]
        
        return {
            "file_path": file_path,
            "file_size": file_size,
            "file_extension": file_extension,
            "content": content,
            "content_truncated": len(content) >= 10000
        }
    except Exception as e:
        return {"error": str(e)}
