<style scoped>
.button {
  background-color: #4caf50;
  border: none;
  color: white;
  padding: 5px 20px;
  text-align: center;
  text-decoration: none;
  display: inline-block;
  cursor: pointer;
  font-weight: bold;
  border-radius: 5px;
  margin: 0 0 5px 0;
}
</style>

<template>
  <div>
    <h1>Direct messages</h1>
    <template v-if="loading">
      <p>
        <img src="/static/img/loading.gif" alt="Loading" />
      </p>
    </template>
    <template v-else>
      <template v-if="isDMAppAuthenticated">
        <h2>Automatically deleting your recent DMs</h2>
        <p>
          Twitter only tells Semiphemeral about the last 30 days of your DMs. Because of this, Semiphemeral can't
          <em>automatically</em> delete all your old DMs, only those within the last 30 days. For example, if you configure it to delete DMs older than 7 days, each time it runs it will delete the DMs between 30 days ago and 7 days ago.
        </p>

        <h2>Deleting all your old DMs</h2>
        <p>
          But don't worry: Semiphemeral can still delete your DMs older than 30 days. You just need to give it a list of all of those DMs. In order to get this list you must
          <a
            href="https://twitter.com/settings/your_twitter_data"
            target="_blank"
          >download your Twitter archive from here</a>. When you request an archive from Twitter it may take them a day or two before it's ready. When it's ready, you will download a zip file containing your archive.
        </p>
        <p>Unzip your Twitter archive. There should be a folder called "data", and inside there should be a file called "direct-message-headers.js" containing the metadata for all of your DMs.</p>
        <p>
          <strong>To delete all of your old DMs, upload your "direct-message-headers.js" file here.</strong> Semiphemeral will delete all your old DMs except for the most recent ones as you've specified in your settings.
        </p>
        <form v-on:submit.prevent="onSubmit">
          <p>
            <input type="file" />
            <input
              v-bind:disabled="loading"
              class="button"
              type="submit"
              value="Delete all my old DMs"
            />
          </p>
        </form>
      </template>
      <template v-else>
        <p>
          If you want to automatically delete your old direct messages you must give Semiphemeral access to your DMs. You can do this on the
          <router-link to="/settings">settings page</router-link>.
        </p>
      </template>
    </template>
  </div>
</template>

<script>
export default {
  props: ["userScreenName"],
  data: function () {
    return {
      loading: false,
      isDMAppAuthenticated: false,
    };
  },
  created: function () {
    this.getDMInfo();
  },
  methods: {
    getDMInfo: function () {
      var that = this;
      that.loading = true;
      fetch("/api/dms")
        .then(function (response) {
          that.loading = false;
          if (response.status !== 200) {
            console.log(
              "Error fetching DM info, status code: " + response.status
            );
            return;
          }
          response.json().then(function (data) {
            that.isDMAppAuthenticated = data["is_dm_app_authenticated"];
          });
        })
        .catch(function (err) {
          console.log("Error fetching DM info", err);
        });
    },
    onSubmit: function () {},
  },
};
</script>