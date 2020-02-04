import Vue from 'vue';
import VueRouter from 'vue-router';

import App from './components/App.vue';
import Dashboard from "./components/pages/Dashboard.vue";
import Tweets from "./components/pages/Tweets.vue";
import Settings from "./components/pages/Settings.vue";
import Tip from "./components/pages/Tip.vue";
import Thanks from "./components/pages/Thanks.vue";

Vue.use(VueRouter);

const router = new VueRouter({
    mode: 'history',
    routes: [
        { path: '/dashboard', name: 'dashboard', component: Dashboard },
        { path: '/tweets', name: 'tweets', component: Tweets },
        { path: '/settings', name: 'settings', component: Settings },
        { path: '/tip', name: 'tip', component: Tip },
        { path: '/thanks', name: 'thanks', component: Thanks }
    ]
});

new Vue({
    el: '#app',
    render: h => h(App),
    router
})
