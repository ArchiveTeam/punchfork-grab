
(function() {
  document.getElementById('source-ingredients').parentNode.onclick = function(e) {
    var tg = (window.event) ? e.srcElement : e.target;
    if (tg.className == 'anchor' && (tg.id == 'categorized' || tg.id == 'source')) {
      document.getElementById('categorized-ingredients').className = (tg.id == 'categorized' ? '' : 'hidden');
      document.getElementById('source-ingredients').className = (tg.id == 'source' ? '' : 'hidden');

      if (!e) var e = window.event;
      e.cancelBubble = true;
      if (e.stopPropagation) e.stopPropagation();
      return false;
    } else {
      return true;
    }
  };
})();

