# Generic example: exporting a table to CSV

> TRAINING EXAMPLE ONLY — This is not verified Friskit documentation. It demonstrates how generic operational knowledge can coexist with product-specific help content.

## Purpose
A common reporting application lets an authorized user export the currently filtered table to a CSV file.

## Example workflow
1. Open the relevant report or data table.
2. Apply filters and date ranges before exporting.
3. Review the visible rows and confirm the selected scope.
4. Choose an export action such as "Export CSV" if available.
5. Wait for the download to finish and open the file in a spreadsheet application.

## Common problems
- If the export is missing rows, check active filters, pagination behaviour, and date range.
- If the export action is unavailable, the user may lack permission or the page may not support CSV export.
- If text appears garbled, check the file encoding; UTF-8 is commonly used.
- Large exports may be processed asynchronously or limited by the application.

## Important boundary
These are generic troubleshooting ideas. Never claim a particular product has an export button, permission, file format, or export limit unless its own documentation confirms it.
