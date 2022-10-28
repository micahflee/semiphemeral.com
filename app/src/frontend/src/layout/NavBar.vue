<script setup>

const props = defineProps({
  userScreenName: String,
  userProfileUrl: String
})

function logoutTitle() {
  return "Logged in as @" + userScreenName.value
}
</script>

<template>
  <div>
    <span class="logo">
      <a href="/">
        <img src="/images/logo-small.png" />
      </a>
    </span>
    <ul>
      <li>
        <router-link to="/dashboard">Dashboard</router-link>
      </li>
      <li>
        <router-link to="/tweets">Tweets</router-link>
      </li>
      <li>
        <router-link to="/export">Export</router-link>
      </li>
      <li>
        <router-link to="/dms">DMs</router-link>
      </li>
      <li>
        <router-link to="/settings">Settings</router-link>
      </li>
      <li>
        <router-link to="/tip">Tip</router-link>
      </li>
      <li>
        <router-link to="/faq">FAQ</router-link>
      </li>
    </ul>
    <span class="user">
      <img v-if="userScreenName" v-bind:src="userProfileUrl" v-bind:title="logoutTitle" />
      <span>
        <a href="/auth/logout">Log out</a>
      </span>
    </span>
  </div>
</template>

<style scoped>
span.logo img {
  vertical-align: middle;
  border: 0;
}

ul {
  display: inline-block;
  list-style: none;
  margin: 0;
  padding: 0;
  vertical-align: middle;
}

ul li {
  display: inline-block;
  padding: 3px 10px;
}

ul li a {
  border: 0;
  background-color: transparent;
  padding: 5px;
  text-decoration: none;
}

ul li a.router-link-active {
  color: #42465d;
  border-bottom: 3px solid #42465d;
}

span.user {
  display: block;
  float: right;
}

span.user img {
  width: 30px;
  border-radius: 50%;
  vertical-align: middle;
}

span.user span {
  vertical-align: middle;
  font-size: 0.8em;
}

span.user span a {
  color: #42465d;
  text-decoration: none;
}
</style>