FROM nginx:latest

COPY ./etc/nginx/nginx.conf /etc/nginx/nginx.conf
COPY ./etc/nginx/conf.d/frontend.conf /etc/nginx/conf.d/frontend.conf

EXPOSE 80
EXPOSE 443

CMD nginx -g 'daemon off;'
