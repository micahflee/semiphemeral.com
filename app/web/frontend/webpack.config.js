const path = require('path');
const VueLoaderPlugin = require('vue-loader/lib/plugin')

module.exports = {
    mode: process.env.DEPLOY_ENVIRONMENT == "production" ? "production" : "development",
    entry: './src/index.js',
    output: {
        path: path.resolve(__dirname, '../static'),
        filename: 'bundle.js'
    },
    module: {
        rules: [
            {
                test: /\.vue$/,
                loader: 'vue-loader'
            },
            {
                test: /\.css$/,
                use: [
                    'vue-style-loader',
                    'css-loader'
                ],
            }
        ]
    },
    plugins: [
        new VueLoaderPlugin()
    ]
};