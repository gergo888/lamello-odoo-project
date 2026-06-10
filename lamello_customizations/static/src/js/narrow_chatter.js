/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";

const narrowChatterService = {
    start() {
        if (session.narrow_chatter) {
            document.body.classList.add("o_user_narrow_chatter");
        }
    },
};

registry.category("services").add("narrow_chatter", narrowChatterService);