sudo pip3 install -r requirements.txt
sudo cp agents_info.conf /etc/supervisor/conf.d/
sudo cp agents_info_nginx.conf /etc/nginx/sites-enabled/
sudo supervisorctl update
sudo systemctl restart nginx
sudo certbot --nginx -d info.ai.medsenger.ru
