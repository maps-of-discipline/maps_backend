#!/usr/bin/env python3
from maps.logic.read_excel import read_excel
import pandas as pd

# Open the Excel file and read the header
filename = '03 - 000020692 - 2024 Автоматизированные системы обработки информации и управления 23.12.2024 15 05 30.xlsx'
with open(filename, 'rb') as f:
    header_df, _ = read_excel(f)
    
print('Header DataFrame content:\n')
print(header_df)
