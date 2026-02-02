sudo zip -r ./bak/freedom-$(date +%Y%m%d).zip ./data/

echo "Backup completed: ./bak/freedom-$(date +%Y%m%d).zip"
echo "File size: $(du -sh ./bak/freedom-$(date +%Y%m%d).zip | awk '{print $1}')"
