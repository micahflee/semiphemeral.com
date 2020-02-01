<template>
  <div class="nav">
    <span class="logo">
      <a href="/">
        <img src="/static/img/logo-small.png" />
      </a>
    </span>
    <ul>
      <li v-for="button in buttons">
        <NavButton
          v-bind="{
                            currentPageComponent: currentPageComponent,
                            buttonText: button.buttonText,
                            pageComponent: button.pageComponent
                        }"
          v-on:select-page="$emit('select-page', button.pageComponent)"
        ></NavButton>
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

<script>
import NavButton from "./NavButton.vue";

export default {
  props: ["currentPageComponent", "userScreenName", "userProfileUrl"],
  data: function() {
    return {
      buttons: [
        { buttonText: "Dashboard", pageComponent: "Dashboard" },
        { buttonText: "Tweets", pageComponent: "Tweets" },
        { buttonText: "Settings", pageComponent: "Settings" },
        { buttonText: "Tip", pageComponent: "Tip" }
      ]
    };
  },
  computed: {
    logoutTitle: function() {
      return "Logged in as @" + this.userScreenName;
    }
  }
};
</script>