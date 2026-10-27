"use client";
import { kt as unstableSetRender } from "./es-GM0xBQNQ.js";
import { t as require_client } from "./client-BGwCFxPD.js";
//#region node_modules/@ant-design/v5-patch-for-react-19/es/index.js
var import_client = require_client();
unstableSetRender(function(node, container) {
	container._reactRoot || (container._reactRoot = (0, import_client.createRoot)(container));
	var root = container._reactRoot;
	root.render(node);
	return function() {
		return new Promise(function(resolve) {
			setTimeout(function() {
				root.unmount();
				resolve();
			}, 0);
		});
	};
});
//#endregion
