import pandas as pd

path = r'data/EC2019_QWsonde_surface_GIS_edited.csv'
df = pd.read_csv(path, encoding='utf-8-sig')
print('=== SHAPE ===')
print('  Rows: %d, Cols: %d' % (len(df), len(df.columns)))

INVALID = -999.9
cols_of_interest = ['pH', 'SpCond_uS_cm', 'Turbidity_NTU', 'Temp_C', 'Latitude_WGS84', 'Longitude_WGS84']

print('\n=== MISSING/INVALID per column ===')
for col in df.columns:
    nan_count = df[col].isna().sum()
    try:
        invalid_count = (df[col] == INVALID).sum()
    except Exception:
        invalid_count = 0
    print('  %s: NaN=%d, -999.9=%d' % (col, nan_count, invalid_count))

print('\n=== VALID ROWS (all 4 params + coords valid) ===')
params = ['pH', 'SpCond_uS_cm', 'Turbidity_NTU', 'Temp_C', 'Latitude_WGS84', 'Longitude_WGS84']
mask = pd.Series([True]*len(df))
for col in params:
    mask = mask & (df[col] != INVALID) & df[col].notna()
valid = df[mask]
print('  Valid rows: %d' % len(valid))

print('\n=== GEOGRAPHIC BOUNDS (valid rows) ===')
print('  Lat: %.6f to %.6f' % (valid['Latitude_WGS84'].min(), valid['Latitude_WGS84'].max()))
print('  Lon: %.6f to %.6f' % (valid['Longitude_WGS84'].min(), valid['Longitude_WGS84'].max()))

print('\n=== PARAMETER RANGES (valid rows) ===')
for col in ['pH', 'SpCond_uS_cm', 'Turbidity_NTU', 'Temp_C']:
    print('  %s: min=%.4f, max=%.4f, mean=%.4f' % (col, valid[col].min(), valid[col].max(), valid[col].mean()))

print('\n=== SAMPLE ROWS (first 3 valid) ===')
print(valid[['Latitude_WGS84','Longitude_WGS84','Temp_C','pH','SpCond_uS_cm','Turbidity_NTU']].head(3).to_string())

print('\n=== TIMESTAMP SAMPLE ===')
print(valid[['Year','Month','Day','Hour','Min','Sec']].head(3).to_string())
