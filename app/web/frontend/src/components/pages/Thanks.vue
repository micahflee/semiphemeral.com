<template>
  <div>
    <h1>Thanks for the tip</h1>
    <p>
      <img src="/static/img/logo.png" />
    </p>
    <p>I'm glad you find this service useful!</p>
    <p v-if="receipt_url">
      <a v-bind:href="receipt_url" target="_blank">Click here</a> for your receipt.
    </p>
  </div>
</template>

<style scoped>
img {
  width: 200px;
  height: 200px;
}

a {
  color: #3333ff;
  text-decoration: underline;
}
</style>

<script>
export default {
  data: function() {
    return {
      receipt_url: null
    };
  },
  created: function() {
    // Get the most recent tip receipt URL
    var that = this;
    fetch("/api/tip/recent")
      .then(function(response) {
        if (response.status !== 200) {
          console.log(
            "Error fetching the most recent tip, status code: " +
              response.status
          );
          return;
        }
        response.json().then(function(data) {
          that.receipt_url = data["receipt_url"];
        });
      })
      .catch(function(err) {
        console.log("Error fetching the most recent tip", err);
      });
  }
};
</script>