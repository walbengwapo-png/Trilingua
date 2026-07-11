#!/bin/bash
# TriLingua Ubuntu + Nginx Setup Script
# Run: bash deploy.sh

set -e

echo "=== Step 1: Install PHP, Nginx deps ==="
sudo apt install -y php8.3-fpm php8.3-cli php8.3-pgsql php8.3-mbstring php8.3-xml php8.3-curl php8.3-zip php8.3-sqlite3

echo "=== Step 2: Install Composer ==="
curl -sS https://getcomposer.org/installer | php
sudo mv composer.phar /usr/local/bin/composer

echo "=== Step 3: Install Node.js ==="
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

echo "=== Step 4: Clone project ==="
cd /var/www
sudo git clone https://github.com/KenUsa-31/Trilingua.git || true
sudo chown -R $USER:$USER /var/www/Trilingua
cd /var/www/Trilingua/trilingua-code

echo "=== Step 5: PHP + Node dependencies ==="
composer install --no-dev --optimize-autoloader
npm install && npm run build

echo "=== Step 6: Laravel setup ==="
cp .env.example .env
php artisan key:generate

echo "=== Updating .env ==="
sed -i 's/APP_ENV=.*/APP_ENV=production/' .env
sed -i 's/APP_DEBUG=.*/APP_DEBUG=false/' .env
sed -i 's|APP_URL=.*|APP_URL=http://'"$(hostname -I | awk '{print $1}')"'|' .env
sed -i 's/DB_CONNECTION=.*/DB_CONNECTION=pgsql/' .env
echo "DB_HOST=db.udpfqvoygmrheikvygqh.supabase.co" >> .env
echo "DB_PORT=5432" >> .env
echo "DB_DATABASE=postgres" >> .env
echo "DB_USERNAME=postgres" >> .env
echo "DB_PASSWORD=Ambotoi31!0" >> .env
echo "DB_SSLMODE=require" >> .env

echo "=== Step 7: Migrate + Permissions ==="
php artisan migrate --force
php artisan config:cache
php artisan route:cache
php artisan view:cache
sudo chown -R www-data:www-data storage bootstrap/cache

echo "=== Step 8: Nginx config ==="
sudo tee /etc/nginx/sites-available/trilingua > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;
    root /var/www/Trilingua/trilingua-code/public;
    index index.php;
    charset utf-8;

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }

    location ~ \.php$ {
        fastcgi_pass unix:/var/run/php/php8.3-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
    }

    location ~ /\.(?!well-known).* {
        deny all;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/trilingua /etc/nginx/sites-enabled/trilingua
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

echo "=== Step 9: Python ==="
sudo apt install -y python3-pip
pip3 install transformers sentencepiece python-docx pdfplumber odfpy striprtf PyMuPDF fastapi uvicorn torch python-multipart

echo "=== Step 10: Python systemd service ==="
sudo tee /etc/systemd/system/trilingua-python.service > /dev/null <<'EOF'
[Unit]
Description=TriLingua Python Translation Server
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/Trilingua/trilingua-code
ExecStart=/usr/bin/python3 Model/server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable trilingua-python
sudo systemctl start trilingua-python

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "========================================="
echo "  Done! Open http://$IP in your browser"
echo "========================================="
