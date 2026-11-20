/* Shared query, sort and pagination state for tables and card collections. */
(function () {
  "use strict";
  EEG.ListController = class {
    constructor(options = {}) {
      this.options = options;
      this.items = Array.from(options.items || []);
      this.state = {query:"", filters:{}, sort:"", page:1, pageSize:Infinity};
    }
    update(changes = {}) {
      this.state = {...this.state, ...changes};
      const state = this.state;
      const query = state.query.trim().toLocaleLowerCase();
      const matches = this.items.filter(item => (!query || String(this.options.searchText?.(item) || "").toLocaleLowerCase().includes(query)) && (!this.options.matches || this.options.matches(item, state.filters)));
      if (this.options.compare) matches.sort((a,b) => this.options.compare(a,b,state.sort));
      const pages = Number.isFinite(state.pageSize) ? Math.max(1,Math.ceil(matches.length/state.pageSize)) : 1;
      state.page = Math.max(1,Math.min(state.page,pages));
      const start = Number.isFinite(state.pageSize) ? (state.page-1)*state.pageSize : 0;
      const result = {matches, items:matches.slice(start,start+state.pageSize), total:matches.length, pages, page:state.page, start};
      this.options.render?.(result);
      return result;
    }
  };
})();
