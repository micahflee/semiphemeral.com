# Getting started

# Containers

## web

This container has nginx, does HTTPS using a Let's Encrypt cert, and forwards traffic to `frontend` and `backend`. Note that this container needs a `.env` file that contains `FRONTEND_DOMAIN` and `BACKEND_DOMAIN` defined.

## frontend

This is the web app frontend, written in next.js. Users register accounts, login, and can change their settings. They can see the progress of fetch and delete jobs, and they can search through their own tweets to choose tweets to manually exclude.

## backend

This is the web app backend server, written in aiohttp.

## jobs

This runs in the background processing jobs. `fetch` jobs download a copy of everyone's tweets; `delete` jobs delete old tweets based on rules.

## db

This runs postgres. Data about is stored here, as well as databases of everyone's tweets. Both `backend` and `jobs` store their data here.
