<?php
require_once __DIR__ . '/hub-const.php';
require_once __DIR__ . '/const.php';
require_once __DIR__ . '/../simplesamlphp/www/_include.php';

$SESSION_NAME = session_name();

$HOP_BY_HOP_HEADERS = array_map('strtolower', [
    "Connection",
    "Keep-Alive",
    "Proxy-Authenticate",
    "Proxy-Authorization",
    "TE",
    "Trailers",
    "Transfer-Encoding",
    "Upgrade"
]);


function redirect_to_hub()
{
    $reproxy_url = HUB_URL.implode('/', array_map('rawurlencode', explode('/', $_SERVER['HTTP_X_REPROXY_URI'])));
    if (array_key_exists('HTTP_X_REPROXY_QUERY', $_SERVER)) {
        $reproxy_url = $reproxy_url.$_SERVER['HTTP_X_REPROXY_QUERY'];
    }
    if ($_SERVER['REQUEST_METHOD'] == 'GET') {
        header("X-Accel-Redirect: /entrance/");
        header("X-Reproxy-URL: ".$reproxy_url);
    } elseif ($_SERVER['REQUEST_METHOD'] == 'POST') {
        $ch = curl_init($reproxy_url);
        if ($_SERVER['HTTPS']) {
            $proto = 'https';
        } else {
            $proto = 'http';
        }
        $headers = array (
            'X-Real-IP: ', $_SERVER['REMOTE_ADDR'],
            'Host: ', $_SERVER['HTTP_HOST'],
            'User-Agent' . $_SERVER['HTTP_USER_AGENT'],
            'Referer' . $_SERVER['HTTP_REFERER'],
            'Origin' . $_SERVER['HTTP_ORIGIN'],
            'Cookie: ' . $_SERVER['HTTP_COOKIE'],
            'X-Forwarded-For: ', $_SERVER['HTTP_X_FORWARDED_FOR'],
            'X-Forwarded-Proto: ', $proto,
            'X-Scheme: ' . $proto,
            'Accept: ' . $_SERVER['HTTP_ACCEPT'],
            'Accept-Encoding: ' . $_SERVER['HTTP_ACCEPT_ENCODING'],
            'Accept-Language: ' . $_SERVER['HTTP_ACCEPT_LANGUAGE'],
        );
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "POST");
        curl_setopt($ch, CURLOPT_HEADER, true);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
        curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
        if ($_SERVER['CONTENT_TYPE'] == 'application/x-www-form-urlencoded') {
            curl_setopt($ch, CURLOPT_POSTFIELDS, $_POST);
        } elseif (str_starts_with($_SERVER['CONTENT_TYPE'], 'multipart/form-data')) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query($_POST));
        }
        $result = curl_exec($ch);

        $info = curl_getinfo($ch);
        $res_header = substr($result, 0, $info["header_size"]);
        $res_body = substr($result, $info["header_size"]);

        http_response_code($info["http_code"]);
        $res_headers = array_slice(explode(PHP_EOL, $res_header), 1);
        foreach($h as $res_headers) {
            $key_value = explode(':', $h, 2);
            if (count($key_value) != 2) {
                continue;
            }
            if (!in_array(strtolower($key_value[0]), $HOP_BY_HOP_HEADERS, true)) {
                header($h);
            }
        }
        http_response_code($info["http_code"]);
        echo $res_body;
        curl_close($ch);
    } else {
        http_response_code(405);
    }
}

/**
 * Redirect to the JupyterHub if local user was authenticated.
 */
function redirect_by_local_user_session()
{
    @session_start();

    if (isset($_SESSION['username'])) {
        // check user entry

        // redirect to hub
        redirect_to_hub();
        exit;
    }
}

/**
 * Redirect to the JupyterHub if Gakunin user was authenticated.
 */
function redirect_by_fed_user_session()
{
    @session_start();

    // if idp metadata file does not exist, cancel the session check.
    if (empty(glob(IDP_METADATA_FILE_PATH))) {
        return;
    }

    $as = new \SimpleSAML\Auth\Simple('default-sp');
    if ($as->isAuthenticated()) {
        // maybe access to other course
        // redirect to authenticator of JupyterHub
        $attributes = $as->getAttributes();
        $mail_address = $attributes[GF_ATTRIBUTES['mail']][0];
        $group_list = $attributes[GF_ATTRIBUTES['isMemberOf']];

        // check authorization
        if (check_authorization($group_list)) {
            $username = get_username_from_mail_address($mail_address);
            header("X-REMOTE-USER: $username");
            redirect_to_hub();
        } else {
            // redirect to message page
            header("X-Accel-Redirect: /no_author");
        }
        exit;
    }
}

/**
 * Logout from the federation
 */
function logout_fed()
{
    $as = new \SimpleSAML\Auth\Simple('default-sp');
    if ($as->isAuthenticated()) {
        $as->logout();
    }
}

/**
 * Check the user autorization of this Coursen
 *
 * @param string $group_list list of groups where a user belongs to
 * @return bool True if user authorized, otherwise False
 */
function check_authorization($group_list)
{
    $result = False;
    if (empty(AUTHOR_GROUP_LIST)) {
        $result = True;
    } else {
       foreach ($group_list as $group) {
           if (in_array($group, AUTHOR_GROUP_LIST)) {
               $result = True;
               break;
           }
       }
    }

    return $result;
}

/**
 * Generate CSRF token based on th session id.
 *
 * @return string  generated token
 */
function generate_token()
{
    return hash('sha256', session_id());
}

/**
 * Validate CSRF token
 *
 * @param string $token  CSRF token
 * @return bool  result of validation
 */
function validate_token($token)
{
    return $token === generate_token();
}

/**
 * Wraper function of the 'htmlspecialchars'
 *
 * @param string $str  source string
 * @return string  entity string
 */
function h($str)
{
    return htmlspecialchars($str, ENT_QUOTES, 'UTF-8');
}

/**
 * Display template page
 *
 *
 *  @param $template template name
 *  @param $vars template variables
 */
function template_page($template, $vars)
{
    $v = $vars;
    include(__DIR__ . "/../templates/" . $template);
}

/**
 * Display error page
 *
 *  @param $title title string
 *  @param $message message string
 */
function error_page($title, $message)
{
    $v = array('title' => $title, 'message' => $message);
    template_page("error_page.html", $v);
}

/**
 * Get local username form user's mail address
 *
 * @param string $str  mail_address
 * @return string  local username
 */
function get_username_from_mail_address($mail_address)
{
    $result = "";

    // Convert to lower and remove characters except for alphabets and digits
    $wk = explode("@", $mail_address);
    $local_part = strtolower($wk[0]);
    $result = preg_replace('/[^a-zA-Z0-9]/', '', $local_part);
    // Add top 6bytes of hash string
    $hash = substr(md5($mail_address), 0, 6);
    $result .= 'x';
    $result .= $hash;

    return $result;
}


function generate_password($length = 10)
{
    $exclude = "/[1I0O\"\'\(\)\^~\\\`\{\}_\?<>]/";

    while(true) {
        $password = exec("pwgen -1ys $length");
        if (preg_match($exclude, $password)) {
            continue;
        }
        break;
    }
    return $password;
}
