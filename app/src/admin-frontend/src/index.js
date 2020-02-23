import Vue from 'vue';
import VueRouter from 'vue-router';

import App from './components/App.vue';
import Users from "./components/pages/Users.vue";
import Fascists from "./components/pages/Fascists.vue";

Vue.use(VueRouter);

const router = new VueRouter({
    mode: 'history',
    routes: [
        { path: '/admin/users', name: 'users', component: Users },
        { path: '/admin/fascists', name: 'fascists', component: Fascists }
    ]
});

new Vue({
    el: '#app',
    render: h => h(App),
    router
})
