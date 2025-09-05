"""
Batch optimization for GPU embeddings
Dynamically determines optimal batch size based on available VRAM
"""
import torch


def get_optimal_batch_size() -> int:
    """
    Determine optimal batch size based on available GPU memory.
    
    Returns:
        Optimal batch size for the available GPU
    """
    if not torch.cuda.is_available():
        print("Warning: CUDA not available, using CPU with small batch size")
        return 16
    
    try:
        # Get GPU properties
        device_props = torch.cuda.get_device_properties(0)
        vram_gb = device_props.total_memory / 1e9
        
        print(f"GPU detected: {device_props.name}")
        print(f"Total VRAM: {vram_gb:.1f} GB")
        
        # Determine batch size based on VRAM
        # These are conservative estimates for MedCPT models
        if vram_gb >= 24:  # High-end GPUs (3090, 4090, A100)
            batch_size = 512
        elif vram_gb >= 16:  # Mid-high GPUs (V100, A6000)
            batch_size = 384
        elif vram_gb >= 12:  # 4070 Ti, 3060 12GB
            batch_size = 256
        elif vram_gb >= 10:  # 3080
            batch_size = 192
        elif vram_gb >= 8:   # 3070, 2080
            batch_size = 128
        elif vram_gb >= 6:   # 2060, 3060 6GB
            batch_size = 64
        else:
            batch_size = 32
        
        # Try to clear cache to get more accurate available memory
        torch.cuda.empty_cache()
        
        # Get available memory (more accurate than total)
        available_memory = torch.cuda.mem_get_info(0)[0] / 1e9
        
        # Adjust if available memory is significantly less than total
        if available_memory < vram_gb * 0.7:  # Less than 70% available
            batch_size = int(batch_size * 0.75)
        
        print(f"Available VRAM: {available_memory:.1f} GB")
        print(f"Selected batch size: {batch_size}")
        
        return batch_size
        
    except Exception as e:
        print(f"Error detecting GPU properties: {e}")
        print("Falling back to conservative batch size")
        return 64


def adaptive_batch_size(initial_batch_size: int, max_retries: int = 3) -> int:
    """
    Adaptively find the maximum batch size that doesn't cause OOM.
    
    Args:
        initial_batch_size: Starting batch size to try
        max_retries: Maximum number of times to reduce batch size
        
    Returns:
        Safe batch size that won't cause OOM
    """
    batch_size = initial_batch_size
    min_batch_size = 8
    
    for retry in range(max_retries):
        try:
            # Try allocating a test tensor
            test_tensor = torch.randn(batch_size, 512, 768).cuda()
            del test_tensor
            torch.cuda.empty_cache()
            return batch_size
        except torch.cuda.OutOfMemoryError:
            # Reduce batch size
            batch_size = max(min_batch_size, batch_size // 2)
            print(f"OOM detected, reducing batch size to {batch_size}")
            torch.cuda.empty_cache()
    
    return min_batch_size


def estimate_memory_usage(batch_size: int, seq_length: int = 512, 
                         hidden_size: int = 768, dtype_bytes: int = 4) -> float:
    """
    Estimate GPU memory usage for a given batch size.
    
    Args:
        batch_size: Number of sequences in batch
        seq_length: Maximum sequence length
        hidden_size: Model hidden dimension
        dtype_bytes: Bytes per element (4 for float32, 2 for float16)
        
    Returns:
        Estimated memory usage in GB
    """
    # Basic tensor size
    tensor_size = batch_size * seq_length * hidden_size * dtype_bytes
    
    # Account for attention matrices and intermediate activations
    # Rule of thumb: ~3-4x the input tensor size for transformer models
    total_size = tensor_size * 3.5
    
    return total_size / 1e9


def get_batch_config():
    """
    Get complete batch configuration for embeddings.
    
    Returns:
        Dictionary with batch configuration
    """
    config = {
        "batch_size": get_optimal_batch_size(),
        "max_seq_length": 512,
        "normalize_embeddings": True,
        "convert_to_numpy": True,
        "show_progress_bar": True,
        "device": "cuda" if torch.cuda.is_available() else "cpu"
    }
    
    # Estimate memory usage
    estimated_gb = estimate_memory_usage(
        config["batch_size"], 
        config["max_seq_length"]
    )
    
    print(f"Estimated memory usage: {estimated_gb:.2f} GB")
    
    # Warn if estimation exceeds available memory
    if torch.cuda.is_available():
        available_gb = torch.cuda.mem_get_info(0)[0] / 1e9
        if estimated_gb > available_gb * 0.9:
            print(f"⚠️  Warning: Estimated usage ({estimated_gb:.1f}GB) may exceed available memory ({available_gb:.1f}GB)")
            print("Consider reducing batch size if OOM occurs")
    
    return config