DIR_NAME="/agent_chat_ui"

git pull
# npm run build
sudo rm -rf "/usr/share/nginx/html${DIR_NAME}"
sudo cp -r  ./out "/usr/share/nginx/html${DIR_NAME}"
sudo chmod -R 777 /usr/share/nginx/html
sudo systemctl restart nginx