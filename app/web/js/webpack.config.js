const path = require('path');

module.exports = {
    mode: process.env.DEPLOY_ENVIRONMENT == "production" ? "production" : "development",
    entry: './src/index.js',
    output: {
        path: path.resolve(__dirname, '../static'),
        filename: 'bundle.js'
    }
};