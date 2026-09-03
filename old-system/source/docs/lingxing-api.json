<!DOCTYPE html>
<html lang="en">

<head>
  <meta charset="UTF-8" />
  <title>Document</title>
  <meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1" />
  <meta name="referrer" content="never" />
  <meta name="description" content="Description" />
  <link rel="icon" href="./favicon.jpg" />
  <meta name="viewport"
    content="width=device-width, user-scalable=no, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0" />
  <link rel="stylesheet" href="/asset/lib/vue.css" />
  <link rel="stylesheet" href="/asset/lib/sidebar.min.css" />
</head>

<body>
  <div id="app">加载中</div>
  <div id="access" style="display: none">
    <div>
      <input id="docAccess" type="text" class="coco-input" placeholder="请输入密钥">
      <div class="">
        <span class="error-text font-red"></span>
      </div>
    </div>
    <div>
    </div>
  </div>
  <script src="/asset/lib/jquery.min.js"></script>
  <script src="/asset/lib/jquery.cookie-1.4.1.min.js"></script>
  <script src="/asset/lib/coco-modal.min.js"></script>
  <script src="/asset/lib/layer.js"></script>
  <script src="/config/env.js"></script>

  <script>
    // 根据localStorage设置语言，默认为中文
    const savedLanguage = window.localStorage.getItem('language') || 'zh'
    window.localStorage.setItem('language', savedLanguage)
    
    var doTranslate = function () { }
    // 加载词库资源
    function loadWordResource() {
      return new Promise(resolve => {
        const src = 'https://static.distributetop.com/assets/erp/js/openapi-en.js'
        const head = document.head || document.getElementsByTagName('head')[0]
        const script = document.createElement('script')
        script.type = 'text/javascript'
        script.src = src
        if (!('onload' in script)) {
          script.onreadystatechange = function () {
            if (this.readyState !== 'complete' && this.readyState !== 'loaded') return
            this.onreadystatechange = null
          }
        }
        script.onload = function () {
          this.onload = null
          resolve()
        }
        head.appendChild(script)
      })
    }

    function initTranslate() {
      const words = window._word_map
      if (!words) return
      // 补充 iframe 页面（在线测试/签名/Token）的翻译词条
      Object.assign(words, {
        '领星系统API在线请求测试': 'LingXing API Online Request Test',
        '领星系统API在线测试': 'LingXing API Online Test',
        '领星系统API生成签名测试': 'LingXing API Signature Generation Test',
        '领星系统API生成Token测试': 'LingXing API Token Generation Test',
        '领星系统生成Token在线测试': 'LingXing Token Generation Online Test',
        '接口请求域名': 'API Request Domain',
        'ℹ️ 接口请求域名': 'ℹ️ API Request Domain',
        '重要提示': 'Important Notice',
        '/pb、/bd 开头接口暂时不可在此页面测试，请使用 Postman、Apifox 等工具测试': 'Interfaces starting with /pb and /bd cannot be tested on this page. Please use Postman, Apifox or other tools.',
        '发送请求': 'Send Request',
        '响应内容': 'Response',
        'Token响应内容': 'Token Response',
        'appSecret和accessToken必填一个': 'Either appSecret or accessToken is required',
        '生成签名': 'Generate Signature',
        '生成Token': '<REDACTED_FEISHU_SPREADSHEET_TOKEN>',
        '复制并填充': 'Copy & Fill',
        '秒级时间戳': 'Unix Timestamp (seconds)',
        '可选，JSON格式': 'Optional, JSON format',
        '实时时间戳': 'Real-time Timestamp',
        '⏰ 实时时间戳': '⏰ Real-time Timestamp',
        '📖 签名生成规则说明': '📖 Signature Generation Rules',
        '步骤1': 'Step 1',
        '步骤2': 'Step 2',
        '步骤3': 'Step 3',
        '步骤4': 'Step 4',
        '步骤5': 'Step 5',
        '步骤6': 'Step 6',
        '步骤7': 'Step 7',
        '📋 步骤1': '📋 Step 1',
        '📋 步骤2': '📋 Step 2',
        '📋 步骤3': '📋 Step 3',
        '📋 步骤4': '📋 Step 4',
        '📋 步骤5': '📋 Step 5',
        '✅ 步骤6': '✅ Step 6',
        '🔗 步骤7': '🔗 Step 7',
        '将所有参数（业务参数 + access_token + app_key + timestamp）按': 'Sort all parameters (business params + access_token + app_key + timestamp) by ',
        'ASCII排序': 'ASCII order',
        '拼接为 key1=value1&key2=value2 格式（': 'Concatenate as key1=value1&key2=value2 format (',
        'value为空不参与，value为null会参与': 'empty values excluded, null values included',
        '对拼接字符串进行': 'Perform ',
        'MD5(32位)加密并转大写': 'MD5 (32-bit) encryption and convert to uppercase',
        '使用': 'Use ',
        '加密MD5值，密钥为': ' to encrypt MD5 value, key is ',
        '对最终签名进行': 'Perform ',
        'URL编码': 'URL encoding',
        '后使用': ' before use',
        '注意': 'Note',
        '⚠️ 注意': '⚠️ Note',
        '签名有效期为2分钟，建议使用实时时间戳生成签名，不要缓存！': 'Signature expires in 2 minutes. Use real-time timestamps to generate signatures. Do not cache!',
        '未编码': 'Unencoded',
        '🔗 拼接参数字符串': '🔗 Concatenated Parameter String',
        '拼接参数字符串': 'Concatenated Parameter String',
        '✅ SIGN': '✅ SIGN',
        '🔗 SIGN-Encoding': '🔗 SIGN-Encoding',
        '将显示拼接后的参数字符串': 'Concatenated parameter string will be displayed here',
        '最终生成的签名': 'Final generated signature',
        'URL编码后的签名，直接用于请求': 'URL-encoded signature, ready for request',
        '解析业务参数ParamsJson': 'Parse business parameters ParamsJson',
        '添加固定参数（access_token、app_key、timestamp）': 'Add fixed parameters (access_token, app_key, timestamp)',
        '参数按照ASCII排序': 'Sort parameters by ASCII',
        '拼接参数字符串（key1=value1&key2=value2...）': 'Concatenate parameter string (key1=value1&key2=value2...)',
        '对拼接字符串进行MD5加密（32位）并转大写': 'MD5 encrypt the concatenated string (32-bit) and convert to uppercase',
        'AES/ECB/PKCS5Padding加密（密钥为AppId）': 'AES/ECB/PKCS5Padding encryption (key is AppId)',
        'URL编码后的签名': 'URL-encoded Signature',
        '将显示解析后的业务参数对象': 'Parsed business parameter object will be displayed here',
        '将显示添加固定参数后的完整参数对象': 'Complete parameter object with fixed params will be displayed here',
        '将显示排序后的参数对象': 'Sorted parameter object will be displayed here',
        '将显示MD5加密后的值（大写）': 'MD5 encrypted value (uppercase) will be displayed here',
        'AES加密后的签名': 'AES encrypted signature',
        'URL编码后的最终签名': 'Final URL-encoded signature',
        'URL编码，用于接口请求': 'URL-encoded, for API requests',
        '点击查看详细的签名生成步骤（7个步骤）': 'Click to view detailed signature generation steps (7 steps)',
      })
      // 提前缓存正则，避免重复执行消耗性能
      const regExps = Object.keys(words).reduce((acc, key) => {
        // 模板型键名
        if (key.indexOf('{0}') > -1) {
          // 循环替换所有{0}
          const reg = new RegExp(key.replace(/\{0\}/g, '(.*)'))
          acc.push({
            expression: reg,
            key
          })
        }
        return acc
      }, [])
      const symbolList = ['-》', '=>', '->', ':', '：', '(', ')', '（', '）', '【', '】', '+', '。', '=', '；']
      const amountExp = new RegExp(/(\d+(.\d+))/g)
      const bracketExp = new RegExp(/([\u4e00-\u9fa5]+)[\(（](￥|\d+)[\)）][:：]?/)
      function tranlate(el = document.body, lang = 'en') {
        if (!el.querySelectorAll) {
          return
        }
        const _trans = (label, type = '') => {
          let text = label?.trim?.()
          // Replace multiple consecutive spaces with a single space
          let singleSpaceText = text.replace(/\s+/g, ' ')
          if (!text) {
            return label
          }
          // 去掉所有空格后尝试匹配（处理"领 星 系 统"这种间隔写法）
          let noSpaceText = text.replace(/\s+/g, '')
          if (words[text]) {
            return words[text]
          } else if (words[singleSpaceText]) {
            return words[singleSpaceText]
          } else if (words[noSpaceText]) {
            return words[noSpaceText]
          } else if (symbolList.some(str => text.includes(str))) {
            for (const symbol of symbolList) {
              if (text.includes(symbol)) {
                if (text.includes('仓库') && symbol === '【') {
                    console.log(1111111111, text)
                  }
                const splitText = text.split(symbol).filter(Boolean).map(t => t.trim())
                if (splitText.length > 0) {
                  return splitText.map(t => _trans(t, type)).join(symbol)
                }
              }
            }
          } else if (text.endsWith?.('：') || text.endsWith?.(':')) {
            const endStr = text[text.length - 1]
            text = text.slice(0, -1)
            if (words[text]) {
              return `${words[text]}${endStr}`
            }
          }
          return label
        }
        for (const node of [...el.querySelectorAll('*')]) {
          // 不能直接修改node.innerText，会导致Vue响应式失效
          if (['path', 'use', 'circle', 'svg', 'symbol', 'STYLE'].includes(node.nodeName) || node.style.display == 'none') {
            continue
          }

          const originalTitle = node.getAttribute('title')
          if (originalTitle) {
            node.setAttribute('title', _trans(originalTitle))
          }
          if (node.nodeName === 'INPUT' && node.type === 'text') {
            node.value = _trans(node.value)
            node.placeholder = _trans(node.placeholder)
          }
          if (node.nodeName === 'TEXTAREA') {
            node.placeholder = _trans(node.placeholder)
          }
          // 运营日志 at输入不要翻译
          if (checkNode(node, 'at-textarea-wrapper') || checkNode(node, 'email-chat-content')) {
            continue
          }
          for (const textNode of [...node.childNodes]) {
            if (textNode.nodeType !== 3) continue
            textNode.textContent = _trans(textNode.textContent)
          }
        }
      }
      tranlate()
      doTranslate = tranlate
    }

    function checkNode(el, id) {
      let node = el
      while (node) {
        const nodeId = node.id
        if (nodeId == id) {
          return true
        }
        node = node.parentNode
      }
      return false
    }

    // 添加语言切换功能
    function addLanguageSwitch() {
      setTimeout(() => {
        console.log(11111)
        const appNav = document.querySelector('.app-nav ul')
        console.log(appNav)
        if (!appNav) return
        
        // 检查是否已经存在语言切换按钮，避免重复添加
        const existingLangSwitch = document.querySelector('.language-switch')
        if (existingLangSwitch) {
          // 如果已经存在，更新当前语言显示
          const currentLang = window.localStorage.getItem('language') || 'zh'
          const selectedLabel = existingLangSwitch.querySelector('.el-select__selected-label')
          const items = existingLangSwitch.querySelectorAll('.el-select__dropdown-item')
          
          if (selectedLabel) {
            selectedLabel.textContent = currentLang === 'en' ? 'EN' : '中文'
          }
          
          // 更新选中状态
          items.forEach(item => {
            const value = item.getAttribute('data-value')
            item.classList.toggle('selected', value === currentLang)
          })
          
          return
        }
        
        const currentLang = window.localStorage.getItem('language') || 'zh'
        
        // 创建语言切换容器
        const langSwitch = document.createElement('div')
        langSwitch.className = 'language-switch'
        langSwitch.innerHTML = `
          <div class="el-select" id="languageSelect">
            <div class="el-select__wrapper">
              <div class="el-select__selection">
                <span class="el-select__selected-label">${currentLang === 'en' ? 'EN' : '中文'}</span>
                <i class="el-select__caret"></i>
              </div>
              <div class="el-select__dropdown" style="display: none;">
                <ul class="el-select__dropdown-list">
                  <div class="el-select__dropdown-item ${currentLang === 'zh' ? 'selected' : ''}" data-value="zh">中文</div>
                  <div class="el-select__dropdown-item ${currentLang === 'en' ? 'selected' : ''}" data-value="en">EN</div>
                </ul>
              </div>
            </div>
          </div>
        `
        
        // 将语言切换添加到导航栏末尾
        appNav.appendChild(langSwitch)
        
        // 绑定自定义下拉事件
        setupCustomSelectEvents()
      }, 500);
    }

    // 设置自定义选择器事件
    function setupCustomSelectEvents() {
      const selectWrapper = document.querySelector('.el-select__wrapper')
      const dropdown = document.querySelector('.el-select__dropdown')
      const selectedLabel = document.querySelector('.el-select__selected-label')
      const items = document.querySelectorAll('.el-select__dropdown-item')
      
      if (!selectWrapper || !dropdown) return
      
      // 清除之前可能存在的事件监听器，避免重复绑定
      selectWrapper.removeEventListener('click', handleSelectClick)
      
      // 点击选择框显示/隐藏下拉
      function handleSelectClick(e) {
        e.stopPropagation()
        const isVisible = dropdown.style.display !== 'none'
        dropdown.style.display = isVisible ? 'none' : 'block'
        selectWrapper.classList.toggle('is-focused', !isVisible)
      }
      
      selectWrapper.addEventListener('click', handleSelectClick)
      
      // 点击选项
      items.forEach(item => {
        item.addEventListener('click', function(e) {
          e.stopPropagation()
          const value = this.getAttribute('data-value')
          const text = this.textContent
          
          // 更新选中状态
          items.forEach(i => i.classList.remove('selected'))
          this.classList.add('selected')
          
          // 更新显示文本
          selectedLabel.textContent = text
          
          // 隐藏下拉
          dropdown.style.display = 'none'
          selectWrapper.classList.remove('is-focused')
          
          // 切换语言
          switchLanguage(value)
        })
      })
      
      // 点击其他地方隐藏下拉
      function handleDocumentClick() {
        if (dropdown) {
          dropdown.style.display = 'none'
        }
        if (selectWrapper) {
          selectWrapper.classList.remove('is-focused')
        }
      }
      
      document.removeEventListener('click', handleDocumentClick)
      document.addEventListener('click', handleDocumentClick)
    }

    // 语言切换逻辑
    async function switchLanguage(lang) {
      window.localStorage.setItem('language', lang)
      
      if (lang === 'en') {
        // 切换到英文，加载翻译资源
        if (!window._word_map) {
          await loadWordResource()
          initTranslate()
        }
        doTranslate()
        translateIframes()
      } else {
        // 切换到中文，清除翻译
        window._word_map = null
        location.reload() // 重新加载页面以显示原始中文内容
      }
    }

    // 翻译页面内所有同源 iframe 的内容
    function translateIframes() {
      var iframes = document.querySelectorAll('.markdown-section iframe')
      iframes.forEach(function (iframe) {
        function doTranslateIframe() {
          try {
            var iframeDoc = iframe.contentDocument || iframe.contentWindow.document
            if (iframeDoc && iframeDoc.body && iframeDoc.body.children.length > 0) {
              doTranslate(iframeDoc.body)
            }
          } catch (e) {
            // 跨域 iframe 忽略
          }
        }
        // 始终监听 load 事件（覆盖导航到 iframe 页面的场景）
        iframe.addEventListener('load', doTranslateIframe)
        // 同时尝试立即翻译（覆盖在当前页面切换语言的场景）
        try {
          var doc = iframe.contentDocument || iframe.contentWindow.document
          if (doc && doc.readyState === 'complete' && doc.body && doc.body.children.length > 0) {
            doTranslateIframe()
          }
        } catch (e) {}
      })
    }

    window.$docsify = {
      loadSidebar: true,
      loadNavbar: true,
      logo: '/asset/img/logo.svg',
      // name: '',
      themeColor: '#1890ff',
      nameLink: 'https://www.asinking.com/',
      repo: '',
      noEmoji: true,
      homepage: '/docs/Guidance/AppID.md',
      //loadSidebar: true,
      subMaxLevel: 3,
      notFoundPage: true,
      pagination: {
        previousText: '上一章节',
        nextText: '下一章节',
        crossChapter: true,
        crossChapterText: true,
      },
      alias: {
        '/.*/_sidebar.md': window.location.href.includes('/map/') ? '/_sidebar_map.md' : '/_sidebar.md',
        '/.*/_navbar.md': '/_navbar.md',
      },
      search: {
        maxAge: 86400000, // 过期时间，单位毫秒，默认一天
        noData: '找不到结果', //搜索不到结果时显示
        paths: 'auto', //自动
        placeholder: '  搜索', //搜索框提示
      },
      copyCode: {
        buttonText: '复制', // 复制按钮的默认文本
        errorText: '错误', // 复制失败时的文本
        successText: '复制成功' // 复制成功时的文本
      },
      mergeNavbar: true,
      plugins: [
        function (hook, vm) {
          function onloadSidebar() {
            // 初始化时调用，只调用一次，没有参数。
            var sidebarPath = '_sidebar.md';
            var previousHash = sessionStorage.getItem('previousHash') || '';
            var currentSidebarType = sessionStorage.getItem('currentSidebarType') || 'docs';
            var isMapRoute = window.location.hash.startsWith('#/map/');
            //layer.msg(previousHash);
            if (isMapRoute) {
              sidebarPath = '_sidebar_map.md';
              // 首次进入地图路由或从文档切换到地图
              if (currentSidebarType !== 'map') {
                sessionStorage.setItem('currentSidebarType', 'map');
                
                // 使用 Docsify 的 API 更新侧边栏
                $.get(sidebarPath).then(function (content) {
                  // 定位侧边栏的元素并更新内容
                  var html = marked(content);
                  var sidebarNav = document.querySelector('.sidebar-nav');
                  if (sidebarNav) {
                    sidebarNav.innerHTML = html;
                    
                    // 手动触发侧边栏初始化和高亮逻辑
                    setTimeout(function() {
                      initMapSidebarStructure();
                    }, 100);
                  }
                });
              } else {
                // 已经在地图路由中，只需要重新高亮当前菜单项
                // 不重新加载侧边栏内容，避免闪烁
                var isMapSidebar = document.querySelector('.sidebar-nav a[href*="/map/"]');
                if (isMapSidebar) {
                  // 侧边栏已经是地图侧边栏，只需更新高亮（不重新加载）
                  updateMapSidebarHighlight();
                } else {
                  // 侧边栏被错误地切换了，需要重新加载
                  $.get(sidebarPath).then(function (content) {
                    var html = marked(content);
                    var sidebarNav = document.querySelector('.sidebar-nav');
                    if (sidebarNav) {
                      sidebarNav.innerHTML = html;
                      setTimeout(function() {
                        initMapSidebarStructure();
                      }, 100);
                    }
                  });
                }
              }
            } else {
              // 从地图切回文档时，需要刷新页面重新加载原始侧边栏
              if (currentSidebarType === 'map') {
                sessionStorage.setItem('currentSidebarType', 'docs');
                location.reload();
              }
            }
          }
          
          // 初始化地图侧边栏结构（首次加载时使用）
          function initMapSidebarStructure() {
            // 1. 添加 folder 和 file 类
            document.querySelectorAll('.sidebar-nav li').forEach(function(li) {
              if (li.querySelector('ul:not(.app-sub-sidebar)')) {
                li.classList.add('folder');
              } else {
                li.classList.add('file');
              }
            });
            
            // 2. 添加 level 类
            function addLevelClass(ul, level) {
              if (!ul) return;
              ul.querySelectorAll(':scope > li').forEach(function(li) {
                if (li.classList.contains('folder')) {
                  li.classList.add('level-' + level);
                  var childUl = li.querySelector(':scope > ul');
                  if (childUl) {
                    addLevelClass(childUl, level + 1);
                  }
                }
              });
            }
            addLevelClass(document.querySelector('.sidebar-nav > ul'), 1);
            
            // 3. 高亮当前菜单项
            updateMapSidebarHighlight();
          }
          
          // 更新地图侧边栏高亮状态（内部导航时使用，不重新加载内容）
          function updateMapSidebarHighlight() {
            // 1. 先移除所有 active 类（但保留 open 状态）
            document.querySelectorAll('.sidebar-nav li.active').forEach(function(li) {
              li.classList.remove('active');
            });
            
            // 2. 找到当前页面对应的菜单项
            var currentHash = window.location.hash;
            var currentLink = document.querySelector('.sidebar-nav a[href="' + currentHash + '"]');
            
            if (currentLink) {
              var li = currentLink.parentElement;
              // 3. 给当前菜单项及其所有父级添加 active 类
              while (li && li.tagName === 'LI') {
                li.classList.add('active');
                // 确保父级菜单是展开的
                if (li.classList.contains('folder') && !li.classList.contains('open')) {
                  li.classList.add('open');
                }
                // 向上查找父级 li
                var parentUl = li.parentElement;
                li = parentUl ? parentUl.closest('li') : null;
              }
            }
          }
          
          hook.init(async function () {
            const currentLanguage = window.localStorage.getItem('language')
            if (currentLanguage === 'en' && !window._word_map) {
              await loadWordResource()
              initTranslate()
            }
            // 初始化时调用，只调用一次，没有参数。
            //onloadSidebar();
          })

          hook.mounted(function () {
            // 初始化完成后调用，只调用一次，没有参数。
            var insert = document.createElement('div')
            insert.innerHTML =
              '<a class="app-name-link" data-nosearch="" target="_blank" href="https://www.asinking.com/"><iframe id="tmp_downloadhelper_iframe" style="display: none;"></iframe></a>'
            var search = document.getElementsByClassName('search')[0]
            document.getElementsByClassName('sidebar')[0].insertBefore(insert, search)
          })

          hook.beforeEach(function (content) {
            // 每次开始解析 Markdown 内容时调用
            // ...
            var docAccessToken = $.cookie('doc_access_token');
            if (docAccessToken) {
              $.ajax({
                url: `${GlobalConfig.apiUrl}/account/check/doc_access/token`,
                type: "PUT",
                data: JSON.stringify({ "docAccess": docAccessToken }),
                dataType: "json",
                headers: {
                  "Content-Type": "application/json",
                  "X-HTTP-Method-Override": "PUT"
                },
                success: function (data) {
                  if (data.data) return content;
                  validKey();
                },
                error: function (err) {
                  if (err.status !== 200) return false;
                  layer.msg(err.responseJSON.msg);
                }
              })
            } else {
              validKey();
            }
            //onloadSidebar();
            function validKey() {
              let docAccess = $("#docAccess");
              coco({
                title: "访问密钥",
                el: "#access",
                cancelButton: false,
                okText: "确定",
                top: "center",
                blur: true,
                maskClose: false,
                escClose: false,
                closeButton: false,
              }).onClose((ok, cc, done) => {
                if (ok) {
                  if (docAccess.val() !== "") {
                    docAccess.removeClass('error');
                    $('.error-text').hide();
                    $.ajax({
                      url: `${GlobalConfig.apiUrl}/account/check/doc_access`,
                      type: "PUT",
                      data: JSON.stringify({ "docAccess": docAccess.val() }),
                      dataType: "json",
                      headers: {
                        "Content-Type": "application/json",
                        "X-HTTP-Method-Override": "PUT"
                      },
                      success: function (data) {
                        if (!data.data) return layer.msg(data.msg);
                        if (!data.data.can_access) return false;
                        $.cookie('doc_access_token', data.data.can_access, { expires: 7 })
                        done();
                      },
                      error: function (err) {
                        layer.msg(err.responseJSON.msg);
                        return false;
                      }
                    })
                  } else {
                    docAccess.addClass('error');
                    $('.error-text').text('请输入访问密钥').show();
                  }
                } else {
                  docAccess.removeClass('error');
                  return false;
                }
              });
            }

          })

          hook.afterEach(function (html, next) {
            // 解析成 html 后调用。beforeEach 和 afterEach 支持处理异步逻辑
            // ...
            // 异步处理完成后调用 next(html) 返回结果
            // console.log(html)
            next(html);
            //onloadSidebar();
          })

          hook.doneEach(function () {
            onloadSidebar();
            var hash = window.location.hash
            if (['#/401', '#/404'].includes(hash)) {
              document.getElementsByClassName('sidebar')[0].style.display = 'none'
              document.getElementsByClassName('app-nav')[0].style.display = 'none'
            } else {
              document.getElementsByClassName('sidebar')[0].style.display = 'block'
              document.getElementsByClassName('app-nav')[0].style.display = 'flex'
              // document.getElementsByClassName('active')[0].className = 'active actives'
              document.getElementsByTagName('html')[0].scrollTop = 0
            }
            
            // 更新顶部导航栏的激活状态
            var isMapRoute = hash.startsWith('#/map/');
            var navLinks = document.querySelectorAll('.app-nav a');
            navLinks.forEach(function(link) {
              link.classList.remove('active');
              var href = link.getAttribute('href');
              // API地图Tab
              if (isMapRoute && href && href.includes('/map/')) {
                link.classList.add('active');
              }
              // API文档Tab（包括根路径和所有非地图路径）
              else if (!isMapRoute && href && (href === '/' || href === '#/' || !href.includes('/map/'))) {
                link.classList.add('active');
              }
            });
            
            // 根据当前语言设置执行翻译
            const currentLanguage = window.localStorage.getItem('language')
            if (currentLanguage === 'en' && window._word_map) {
              doTranslate()
              translateIframes()
            }
            
            // 确保每次路由变化后都有语言切换按钮
            addLanguageSwitch()
          })

          hook.ready(function () {

          })
        },
      ],
      // loadNavbar: true
    }

    /*document.addEventListener('click', function(event) {
      if (event.target.tagName === 'A' && event.target.href.includes('#')) {
        sessionStorage.setItem('previousHash', window.location.hash);
        //layer.msg(sessionStorage.getItem('previousHash'));
      }
    });*/

  </script>

  <script src="/asset/lib/docsify.min.js"></script>
  <script src="/asset/lib/docsify-sidebar-collapse.min.js"></script>
  <script src="/asset/lib/search.js"></script>
  <script src="/asset/lib/docsify-pagination.min.js"></script>
  <script src="//cdn.jsdelivr.net/npm/docsify-copy-code/dist/docsify-copy-code.min.js"></script>
  <!-- <script src="/asset/lib/vue.min.js"></script> -->
  <script src="/asset/lib/zoom-image.js"></script>

  <style>
    pre {
      overflow-y: auto;
      max-height: 400px;
    }
  </style>

  <style>
    .docsify-copy-code-button {
      background-color: #e6e5e5;
      /* 按钮背景颜色 */
      color: #574747;
      /* 按钮文字颜色 */
      border: none;
      /* 去掉边框 */
      border-radius: 4px;
      /* 圆角边框 */
      padding: 5px 10px;
      /* 内边距 */
      margin: 0 5px;
      /* 外边距 */
      cursor: pointer;
      /* 鼠标悬停时显示手形光标 */
      /* ... 其他你想要添加的样式 ... */
    }
  </style>

  <style type="text/css">
    .big-logo {
      width: 50%;
    }

    .big-logo>img {
      box-shadow: none !important;
    }

    .hide {
      display: none;
    }

    .show {
      display: block;
    }

    .font-red {
      color: red;
    }

    .sidebar-nav {
      overflow-y: auto;
      overflow-x: hidden;
      height: calc(100% - 120px);
    }

    .sidebar-nav::-webkit-scrollbar {
      width: 4px;
    }

    .sidebar-nav::-webkit-scrollbar-thumb {
      background: transparent;
      border-radius: 4px;
    }

    .sidebar-nav:hover::-webkit-scrollbar-thumb {
      background: hsla(0, 0%, 53.3%, 0.4);
    }

    .sidebar-nav:hover::-webkit-scrollbar-track {
      background: hsla(0, 0%, 53.3%, 0.1);
    }

    .sidebar-nav>ul>li>a {
      font-weight: 600 !important;
    }

    .register {
      cursor: pointer;
      width: 80px;
      height: 32px;
      background: linear-gradient(270deg, #ff9783 0%, #ff613d 100%);
      border-radius: 18px;
      color: #fff;
      font-size: 14px;
      line-height: 32px;
      text-align: center;
    }

    .register a:hover {
      color: #fff;
    }

    .app-nav a.active {
      border-bottom-color: #174cb4;
      color: #174cb4;
    }

    .sidebar>div:nth-child(1) {
      display: flex;
      margin-top: 23px;
      justify-content: center;
      /* padding-right: 20px; */
    }

    .search {
      border: none;
      margin: 16px 0 0 0;
    }

    .search input {
      border-radius: 18px;
      width: 208px;
      height: 32px;
      background: rgba(244, 247, 255, 1);
    }

    .search input:focus {
      box-shadow: none;
    }

    .app-nav.no-badge {
      margin: 0 auto;
      right: calc(50% - 590px);
      height: 63px;
      display: flex;
      align-items: center;
      /* padding: 14px 0; */
    }

    body.sticky .sidebar {
      /* top: 56px; */
      align-items: center;
      height: 100%;
    }

    .app-nav a {
      font-size: 14px;
      align-items: center;
      height: 100%;
      padding: 23px 0 0 0;
    }

    .sidebar li {
      font-weight: 600;
    }

    .center {
      text-align: center;
    }

    .weight {
      font-weight: 600;
    }

    .bottom-30 {
      margin-bottom: 30px !important;
    }

    .no-left {
      margin-left: 0 !important;
    }

    .sidebar ul li.active>a {
      font-weight: 400;
    }

    @media (max-width: 768px) {
      .app-nav.no-badge {
        display: none;
      }
    }

    @media (min-width: 769px) {
      .app-nav.no-badge {
        right: 0;
      }

      .actives {
        margin-right: 40px !important;
      }

      .app-nav>a {
        margin: 0 15px 0 0;
      }
    }

    @media (min-width: 890px) {
      .app-nav.no-badge {
        right: 0;
      }

      .actives {
        margin-right: 60px !important;
      }

      .app-nav>a {
        margin: 0 25px 0 0;
      }
    }

    @media (min-width: 1000px) {
      .app-nav.no-badge {
        right: 0;
      }

      .app-nav>a {
        margin: 0 40px 0 0;
      }
    }

    @media (min-width: 1200px) {
      .app-nav.no-badge {
        right: calc(50% - 590px);
      }

      .app-nav>a {
        margin: 0 50px 0 0;
      }
    }

    @media (min-width: 1175px) {
      .content {
        padding-right: 125px !important;
      }

      ul.app-sub-sidebar>li>a {
        font-size: 13px !important;
        /* width: 140px !important; */
      }

      ul.app-sub-sidebar {
        right: 40px;
      }

      .sidebar {
        left: 50px;
      }
    }

    @media (max-width: 1175px) {
      .app-sub-sidebar {
        display: none;
      }
    }

    @media (min-height: 890px) {
      .sidebar-nav ul:not(.app-sub-sidebar)>li {
        line-height: 42px;
      }

      .sidebar-nav ul:not(.app-sub-sidebar)>li:not(.file)::before {
        top: 17px;
      }

      .sidebar-nav ul:not(.app-sub-sidebar)>li.open::before {
        top: 16px;
      }
    }

    video {
      max-width: 80%;
    }

    .markdown-section {
      color: #0d1a26 !important;
      font-family: Segoe UI, Roboto, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Helvetica Neue, Helvetica, Arial, sans-serif;
    }

    .markdown-section table {
      margin-left: 24px;
    }

    .anchor span {
      color: #0d1a26 !important;
      font-family: Segoe UI, Roboto, PingFang SC, Hiragino Sans GB, Microsoft YaHei, Helvetica Neue, Helvetica, Arial, sans-serif;
    }

    .markdown-section img {
      -webkit-box-shadow: 0 1px 6px rgba(0, 0, 0, 0.2);
      box-shadow: 0 1px 6px rgba(0, 0, 0, 0.2);
      margin: 5px 0;
    }

    .app-name-link {
      color: #1890ff !important;
      background-image: url(/asset/img/logo.svg);
      width: 200px;
      height: 22px;
      background-size: contain;
      background-repeat: no-repeat;
      margin-right: -2px;
    }

    .sidebar {
      width: auto;
      max-width: 400px;
    }

    .level-1.folder.open>ul>li.open>a {
      background-color: #f4f7ff !important;
      color: #174cb4 !important;
    }

    ul li.active>a {
      background-color: #f4f7ff !important;
      color: #174cb4 !important;
    }

    @media screen and (max-width: 980px) {
      .app-sub-sidebar {
        display: none;
      }

      .app-sub-sidebar li:before {
        content: none;
      }

      .qidian_wpa_img {
        width: 30px !important;
        height: 30px !important;
        bottom: 8px !important;
        right: 6px !important;
      }
    }

    @media screen and (min-width: 980px) {
      .sidebar-toggle-button {
        display: none;
      }

      .sidebar ul li a {
        width: auto;
        margin-left: -30px;
        padding-left: 30px;
      }

      .qidian_wpa_img {
        bottom: 70px !important;
      }

      ul li.actives>a {
        font-weight: 400 !important;
        background-color: #e6f7ff;
        border-right: 2px solid;
        color: #174cb4;
      }

      .app-sub-sidebar {
        position: fixed;
        right: 8px;
        top: 120px;
      }

      .content {
        left: 300px !important;
        padding-right: 50px;
      }

      .sidebar-toggle {
        max-width: 229px;
      }

      ul.app-sub-sidebar li {
        margin: 0;
        padding: 4px 0;
        border-left: 1px solid #f0f0f0;
      }

      ul.app-sub-sidebar li a {
        margin-left: 0px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        width: 115px;
        padding-left: 14px !important;
        font-size: 12px;
        line-height: 18px;
      }

      ul.app-sub-sidebar li.active a {
        background-color: #fff !important;
        border-right: none !important;
        border-left: 1px solid;
      }

      .app-sub-sidebar li:before {
        content: none;
      }
    }

    @media (min-width: 768px) {
      .content {
        left: 300px !important;
      }

      .sidebar {
        border-right: none;
        /* border-right: 1px solid rgba(0, 0, 0, 0.04); */
        overflow-x: hidden;
      }

      .input-wrap {
        background-color: #fff;
      }

      .clear-button {
        cursor: pointer;
        padding: 3px 2px 0 0;
        box-sizing: border-box;
      }

      .search .clear-button svg {
        transform: scale(0.7);
      }

      .markdown-section {
        color: rgba(0, 0, 0, 0.85);
        font-size: 14px;
        line-height: 2;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol',
          'Noto Color Emoji';
      }

      .markdown-section p.tip:before {
        width: 0;
        /* display: none; */
      }

      .markdown-section p.tip {
        border-left: none;
        background-color: #f0f5ff;
        padding: 14px 24px 14px 30px;
      }

      .highlight {
        line-height: 1.5;
      }

      .markdown-section p {
        margin: 0.8rem 0 !important;
      }

      .markdown-section h1,
      .markdown-section h1>a {
        margin-top: 8px;
        margin-bottom: 20px;
        color: rgba(0, 0, 0, 0.85);
        font-weight: 600 !important;
        border: none !important;
        font-size: 30px;
      }

      .markdown-section h1 .subtitle {
        margin-left: 12px;
      }

      .anchor span {
        color: rgba(0, 0, 0, 0.85);
      }

      .ant-row-rtl .markdown-section h1 .subtitle {
        margin-right: 12px;
        margin-left: 0;
      }

      .markdown-section h2,
      .markdown-section h2>a {
        font-size: 20px;
        line-height: 32px;
        font-weight: 600 !important;
        color: #0d1a26;
      }

      .markdown-section blockquote {
        border-color: #ced4d9;
      }

      .markdown-section h2,
      .markdown-section h3,
      .markdown-section h4,
      .markdown-section h5,
      .markdown-section h6 {
        clear: both;
        margin: 1.4em 0 0.4em;
        color: rgba(0, 0, 0, 0.85);
        font-weight: 500;
        font-family: Avenir, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif, 'Apple Color Emoji', 'Segoe UI
 Emoji', ' Segoe UI Symbol',
 'Noto Color Emoji', sans-serif;
      }

      .markdown-section h3 {
        font-size: 20px;
      }

      .markdown-section h4 {
        font-size: 15px;
        line-height: 15px;
      }

      .markdown-section code {
        color: #1890ff;
      }

      .markdown-section h5 {
        font-size: 14px;
      }

      .markdown-section h6 {
        font-size: 12px;
      }

      .markdown-section hr {
        clear: both;
        height: 1px;
        margin: 56px 0;
        background: #f0f0f0;
        border: 0;
      }

      .markdown-section p,
      .markdown-section pre {
        margin: 1em 0;
      }

      .markdown-section ul>li,
      .markdown-section ol>li {
        margin-left: 2px;
      }

      ol ul {
        list-style-type: disc;
      }

      /* .ant-row-rtl .markdown-section ul > li {
          margin-right: 20px;
          margin-left: 0;
          padding-right: 4px;
          padding-left: 0;
          }
          .markdown-section ul > li:empty {
          display: none;
          }
          .markdown-section ol > li {
          margin-left: 20px;
          padding-left: 4px;
          list-style-type: decimal;
          }
          .ant-row-rtl .markdown-section ol > li {
          margin-right: 20px;
          margin-left: 0;
          padding-right: 4px;
          padding-left: 0;
          }
          .markdown-section ul > li > p,
          .markdown-section ol > li > p {
          margin: 0.2em 0;
          }
          .markdown-section code {
          margin: 0 1px;
          padding: 0.2em 0.4em;
          font-size: 0.9em;
          background: #f2f4f5;
          border: 1px solid #f0f0f0;
          border-radius: 3px;
          }
          .markdown-section pre {
          font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, Courier, monospace;
          background: #f2f4f5;
          border-radius: 2px;
          }
          .markdown-section pre code {
          margin: 0;
          padding: 0;
          overflow: auto;
          color: rgba(0, 0, 0, 0.85);
          font-size: 13px;
          background: #f5f5f5;
          border: none;
          }
          .markdown-section strong,
          .markdown-section b {
          font-weight: 500;
          }
          .markdown-section > table {
          width: 100%;
          margin: 8px 0 16px;
          empty-cells: show;
          border: 1px solid #f0f0f0;
          border-collapse: collapse;
          border-spacing: 0;
          }
          .markdown-section > table th {
          color: #5c6b77;
          font-weight: 500;
          white-space: nowrap;
          background: rgba(0, 0, 0, 0.02);
          }
          .markdown-section > table th,
          .markdown-section > table td {
          padding: 16px 24px;
          text-align: left;
          border: 1px solid #f0f0f0;
          }
          .markdown-section blockquote {
          margin: 1em 0;
          padding-left: 0.8em;
          color: rgba(0, 0, 0, 0.45);
          font-size: 90%;
          border-left: 4px solid #f0f0f0;
          }
          .ant-row-rtl .markdown-section blockquote {
          padding-right: 0.8em;
          padding-left: 0;
          border-right: 4px solid #f0f0f0;
          border-left: none;
          }
          .markdown-section blockquote p {
          margin: 0;
          }
          .markdown-section .anchor {
          margin-left: 8px;
          opacity: 0;
          -webkit-transition: opacity 0.3s;
          transition: opacity 0.3s;
          }
          .ant-row-rtl .markdown-section .anchor {
          margin-right: 8px;
          margin-left: 0;
          }
          .markdown-section .waiting {
          color: #ccc;
          cursor: not-allowed;
          }
          .markdown-section a.edit-button {
          display: inline-block;
          margin-left: 8px;
          text-decoration: none;
          }
          .ant-row-rtl .markdown-section a.edit-button {
          margin-right: 8px;
          margin-left: 0;
          }
          .markdown-section a.edit-button i {
          color: rgba(0, 0, 0, 0.45);
          }
          .markdown-section a.edit-button .anticon {
          display: block;
          font-size: 16px;
          }
          .markdown-section > br,
          .markdown-section > p > br {
          clear: both;
          } */
    }

    @media (min-width: 1440px) {
      ul.app-sub-sidebar {
        right: 40px;
      }

      ul.app-sub-sidebar li a {
        width: 175px;
      }
    }

    /* 语言切换样式 - Element UI风格 */
    .language-switch {
      display: inline-block;
      margin-left: 15px;
      position: relative;
    }

    .el-select {
      position: relative;
      display: inline-block;
    }

    .el-select__wrapper {
      position: relative;
      cursor: pointer;
      background-color: #ffffff;
      border: 1px solid #dcdfe6;
      border-radius: 4px;
      padding: 0 15px;
      font-size: 14px;
      color: #606266;
      outline: none;
      min-width: 100px;
      height: 40px;
      line-height: 40px;
      transition: border-color 0.3s, box-shadow 0.3s;
      box-sizing: border-box;
    }

    .el-select__wrapper:hover {
      border-color: #c0c4cc;
    }

    .el-select__wrapper.is-focused {
      border-color: #005eff;
      box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
    }

    .el-select__selection {
      display: flex;
      align-items: center;
      justify-content: space-between;
      height: 100%;
    }

    .el-select__selected-label {
      flex: 1;
      text-align: left;
      color: #606266;
      font-size: 16px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .el-select__caret {
      width: 0;
      height: 0;
      border-left: 5px solid transparent;
      border-right: 5px solid transparent;
      border-top: 5px solid #c0c4cc;
      transition: transform 0.3s;
      margin-left: 8px;
    }

    .el-select__wrapper.is-focused .el-select__caret {
      transform: rotate(180deg);
    }

    .el-select__dropdown {
      position: absolute;
      top: calc(100% + 2px);
      left: 0;
      right: 0;
      background: #ffffff;
      border: 1px solid #e4e7ed;
      border-radius: 4px;
      box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
      z-index: 9999;
      max-height: 200px;
      overflow-y: auto;
    }

    .el-select__dropdown-list {
      list-style: none;
      width: 100%;
      padding: 6px 0;
      margin: 0;
      box-sizing: border-box;
    }

    .el-select__dropdown-item {
      list-style: none;
      width: 100%;
      box-sizing: border-box;
      height: 34px;
      line-height: 34px;
      font-size: 16px;
      color: #606266;
      padding: 0 10px !important;
      cursor: pointer;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      transition: background-color 0.3s;
      margin: 0 !important;
      text-align: left;
    }

    .el-select__dropdown-item:hover {
      background-color: #f5f7fa;
    }

    .el-select__dropdown-item.selected {
      color: #005eff;
      font-weight: 600;
      background-color: #e5eefe;
    }

    .el-select__dropdown-item.selected::after {
      content: '✓';
      float: right;
      color: #005eff;
      font-weight: bold;
    }

    @media (max-width: 768px) {
      .language-switch {
        margin-left: 10px;
      }
      
      .el-select__wrapper {
        font-size: 13px;
        height: 32px;
        line-height: 32px;
        min-width: 80px;
        padding: 0 10px;
      }

      .el-select__selected-label {
        font-size: 13px;
      }

      .el-select__dropdown-item {
        height: 30px;
        line-height: 30px;
        padding: 0 15px;
        font-size: 13px;
      }
    }
  </style>
</body>

</html>