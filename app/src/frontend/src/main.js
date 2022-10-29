import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue';
import Dashboard from "./pages/Dashboard.vue";
import Tweets from "./pages/Tweets.vue";
import Export from "./pages/Export.vue";
import DirectMessages from "./pages/DirectMessages.vue";
import Settings from "./pages/Settings.vue";
import Tip from "./pages/Tip.vue";
import Thanks from "./pages/Thanks.vue";
import CancelTip from "./pages/CancelTip.vue";
import Faq from "./pages/Faq.vue";

const routes = [
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

const router = createRouter({
    history: createWebHistory(),
    routes
})

const app = createApp(App)
app.use(router)
app.mount('#app')