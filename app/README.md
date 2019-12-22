# Containers

## web

This is the web app. Users register accounts, login, and can change their settings. They can see the progress of fetch and delete jobs, and they can search through their own tweets to choose tweets to manually exclude.

## jobs

This runs in the background processing jobs. `fetch` jobs download a copy of everyone's tweets; `delete` jobs delete old tweets based on rules.

## db

This runs postgres. Data about users (from web) is stored here, as well as databases of everyone's tweets. Both `web` and `jobs` store their data here.
