import pandas as pd

# Read your data
df = pd.read_csv(r"C:\Users\OBUYA\Desktop\Hackerthorn\NewCHIRPS_Monthly_Rainfall_2000_2024.csv")

print("Original data:")
print(df.head())

# Extract numbers from @id column (removes "relation/" or "way/" prefix)
df['id_number'] = df['@id'].str.split('/').str[1].astype(int)

print("\nData with extracted id_number:")
print(df[['@id', 'id_number']].head(10))

# Save the result
df.to_csv(r"C:\Users\OBUYA\Desktop\Hackerthorn\output.csv", index=False)

print("\nDone! File saved as output.csv")
print(f"Total rows processed: {len(df)}")