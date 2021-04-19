import Vue from 'vue';
import VueRouter from 'vue-router';

import App from './components/App.vue';
import Dashboard from "./components/pages/Dashboard.vue";
import Tweets from "./components/pages/Tweets.vue";
import Export from "./components/pages/Export.vue";
import DirectMessages from "./components/pages/DirectMessages.vue";
import Settings from "./components/pages/Settings.vue";
import Tip from "./components/pages/Tip.vue";
import Thanks from "./components/pages/Thanks.vue";
import CancelTip from "./components/pages/CancelTip.vue";
import Faq from "./components/pages/Faq.vue";

Vue.use(VueRouter);

const router = new VueRouter({
    mode: 'history',
    routes: [
        { path: '/dashboard', name: 'dashboard', component: Dashboard },
        { path: '/tweets', name: 'tweets', component: Tweets },
        { path: '/export', name: 'export', component: Export },
        { path: '/dms', name: 'dms', component: DirectMessages },
        { path: '/settings', name: 'settings', component: Settings },
        { path: '/tip', name: 'tip', component: Tip },
        { path: '/thanks', name: 'thanks', component: Thanks },
        { path: '/cancel-tip', name: 'cancel-tip', component: CancelTip },
        { path: '/faq', name: 'faq', component: Faq }
    ]
});

new Vue({
    el: '#app',
    render: h => h(App),
    router
})
