dofile("urlcode.lua")
JSON = (loadfile "JSON.lua")()

read_file = function(file)
  if file then
    local f = io.open(file)
    local data = f:read("*all")
    f:close()
    return data
  else
    return ""
  end
end

url_count = 0

previous_stats = ""

print_stats = function()
  s = " - Downloaded: "..url_count
  s = s.." URLs."
  if s ~= previous_stats then
    io.stdout:write("\r"..s)
    io.stdout:flush()
    previous_stats = s
  end
end

wget.callbacks.get_urls = function(file, url, is_css, iri)
  local urls = {}

  -- progress message
  url_count = url_count + 1
  if url_count % 10 == 0 then
    print_stats()
  end

  -- user -- main likes page
  local username = string.match(url, "^http://punchfork.com/likes/([^/]+)$")
  if username then
    -- profile page
    table.insert(urls, { url=("http://punchfork.com/"..username), link_expect_html=1 })

    -- some of the different likes pages
    table.insert(urls, { url=("http://punchfork.com/likes/"..username.."/new"), link_expect_html=1 })
    table.insert(urls, { url=("http://punchfork.com/likes/"..username.."/trending"), link_expect_html=1 })
    table.insert(urls, { url=("http://punchfork.com/likes/"..username.."/mostliked"), link_expect_html=1 })
    table.insert(urls, { url=("http://punchfork.com/likes/"..username.."/top"), link_expect_html=1 })

    -- get full list of likes
    table.insert(urls, { url=("http://punchfork.com/api/rc?query="..cgilua.urlcode.escape("likes/"..username.."/new").."&size=100&start="..cgilua.urlcode.escape("2013-12-01T00:00:00")) })
  end

  -- user likes API
  local base = string.match(url, "^(http://punchfork.com/api/rc%?query=likes.+new&size=100)&start=.+")
  if base then
    local json = JSON:decode(read_file(file))

    -- process recipes
    for i, card in pairs(json["cards"]) do
      for recipe_url in string.gmatch(card, "\"(/recipe/[^/\"]+)\"") do
        table.insert(urls, { url=("http://punchfork.com"..recipe_url), link_expect_html=1 })
      end
      for recipe_image_url in string.gmatch(card, "src=\"(http://[^\"]+)\"") do
        table.insert(urls, { url=recipe_image_url })
      end
    end

    if #(json["cards"]) == 100 then
      -- next date
      table.insert(urls, { url=(base.."&start="..cgilua.urlcode.escape(json["next"])) })
    end
  end

  -- general new API (we use this as the tracker's queue)
  local base = string.match(url, "^(http://punchfork.com/api/rc%?query=new&size=100)&start=.+")
  if base then
    local json = JSON:decode(read_file(file))

    -- process recipes
    for i, card in pairs(json["cards"]) do
      for recipe_url in string.gmatch(card, "\"(/recipe/[^/\"]+)\"") do
        table.insert(urls, { url=("http://punchfork.com"..recipe_url), link_expect_html=1 })
      end
      for recipe_image_url in string.gmatch(card, "src=\"(http://[^\"]+)\"") do
        table.insert(urls, { url=recipe_image_url })
      end
    end
  end

  -- recipe
  local base = string.match(url, "^http://punchfork.com/recipe/[^/]+$")
  if base then
    local html = read_file(file)

    local redir_url = string.match(html, "href=\"(/r%?[^\"]+)\"")
    if redir_url then
      table.insert(urls, { url=("http://punchfork.com"..redir_url), link_expect_html=1 })
    end

    local shortlink_url = string.match(html, "id=\"shortlink%-url\"[^>]+value=\"([^\"]+)\"")
    if shortlink_url then
      table.insert(urls, { url=shortlink_url })
    end
  end

  return urls
end

