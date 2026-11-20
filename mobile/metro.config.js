// expo-sqlite 的 web worker 需要把 .wasm 作为资产解析（原生端不受影响）。
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
config.resolver.assetExts.push('wasm');

module.exports = config;
