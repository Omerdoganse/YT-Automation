#!/bin/sh
# Göndermeden önce gizli bilgi taraması: bulursa durur.
if grep -rnE "AQ\.Ab8|AIza[0-9A-Za-z_-]{30}|GOCSPX-|ya29\.|\"refresh_token\"|client_secret\"\s*:" --exclude=guvenlik_kontrol.sh --exclude-dir=.git . ; then
  echo "GİZLİ BİLGİ BULUNDU - gönderilmedi"; exit 1
fi
echo "temiz"
