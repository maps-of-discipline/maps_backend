def index_to_column_letter(index):
    """
    Convert Excel column index to letter.
    :param index: Index of the column (0-based).
    :return: Column letter.
    """
    if index < 0:
        raise ValueError("Column index must be non-negative")

    result = []
    while index >= 0:
        index, remainder = divmod(index, 26)
        result.append(chr(65 + remainder))  # ASCII 'A' is 65
        index -= 1  # Adjust for 0-based index

    return ''.join(reversed(result))