def receipt_total(prices, discount_rate=0):
    if not 0 <= discount_rate <= 1:
        raise ValueError("discount_rate must be between 0 and 1")
    return sum(prices) * (1 - discount_rate)
