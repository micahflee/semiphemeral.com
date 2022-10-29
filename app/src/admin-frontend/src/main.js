import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'

import App from './App.vue';
import Home from "./pages/Home.vue";
import Jobs from "./pages/Jobs.vue";
import Users from "./pages/Users.vue";
import Fascists from "./pages/Fascists.vue";
import Tips from "./pages/Tips.vue";

const routes = [
    { path: '/', name: 'home', component: Home },
    { path: '/jobs', name: 'jobs', component: Jobs },
    { path: '/users', name: 'users', component: Users },
    { path: '/fascists', name: 'fascists', component: Fascists },
    { path: '/tips', name: 'tips', component: Tips }
]

const router = createRouter({
    history: createWebHashHistory(),
    routes
})

const app = createApp(App)
app.use(router)
app.mount('#app')