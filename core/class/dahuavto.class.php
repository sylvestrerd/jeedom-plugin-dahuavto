<?php

/* This file is part of Jeedom.
 *
 * Jeedom is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * Jeedom is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with Jeedom. If not, see <http://www.gnu.org/licenses/>.
 */

/* * ***************************Includes********************************* */
require_once __DIR__  . '/../../../../core/php/core.inc.php';

class dahuavto extends eqLogic {
   
    /*     * ***********************Methode static*************************** */

    public static function dependancy_info() {
		$return = array();
		$return['log'] = log::getPathToLog(__CLASS__.'_update');
		$return['progress_file'] = jeedom::getTmpFolder(__CLASS__) . '/dependancy';
		$return['state'] = 'ok';
        if (file_exists(jeedom::getTmpFolder(__CLASS__) . '/dependency')) {
			$return['state'] = 'in_progress';
		}
        else {
            if (exec(system::getCmdSudo() . system::get('cmd_check') . '-E "python3\-requests" | wc -l') < 1) {
                $return['state'] = 'nok';
            }
            if (exec(system::getCmdSudo() . 'pip3 list | grep -E "requests|pyudev" | wc -l') < 2) {
                $return['state'] = 'nok';
            }
        }
		return $return;
	}

	public static function dependancy_install() {
		log::remove(__CLASS__ . '_update');
		return array(
            'script' => dirname(__FILE__) . '/../../resources/install_#stype#.sh ' . jeedom::getTmpFolder(__CLASS__) . '/dependancy',
            'log' => log::getPathToLog(__CLASS__ . '_update')
        );
	}

    public static function deamon_start() {
		self::deamon_stop();
		$daemon_info = self::deamon_info();
		$daemon_path = realpath(dirname(__FILE__) . '/../../resources/dahuavto');
		$cmd = 'sudo /usr/bin/python3 ' . $daemon_path . '/daemon.py';
		$cmd .= ' --loglevel ' . log::convertLogLevel(log::getLogLevel(__CLASS__));
		// $cmd .= ' --device ' . $device;
		$cmd .= ' --socketport ' . config::byKey('socketport', __CLASS__);
		$cmd .= ' --sockethost 127.0.0.1';
		$cmd .= ' --callback ' . network::getNetworkAccess('internal', 'proto:127.0.0.1:port:comp') . '/plugins/dahuavto/core/php/dahuavto.php';
		$cmd .= ' --apikey ' . jeedom::getApiKey(__CLASS__);
		$cmd .= ' --daemonname local';
		$cmd .= ' --pid ' . jeedom::getTmpFolder(__CLASS__) . '/daemon.pid';
		log::add(__CLASS__, 'info', 'Launching dahuavto daemon : ' . $cmd);
		$result = exec($cmd . ' >> ' . log::getPathToLog('dahuavto_daemon') . ' 2>&1 &');
		$i = 0;
		while ($i < 30) {
			$daemon_info = self::deamon_info();
			if ($daemon_info['state'] == 'ok') {
				break;
			}
			sleep(1);
			$i++;
		}
		if ($i >= 30) {
			log::add(__CLASS__, 'error', __('Unable to start dahuavto daemon, check the logs',__FILE__), 'unableStartdaemon');
			return false;
		}
		message::removeAll(__CLASS__, 'unableStartdaemon');

        foreach (self::byType(__CLASS__) as $device) {
            $device->sendToDaemon('add');
        }

		return true;
    }

    public static function deamon_stop() {
		$pid_file = '/tmp/dahuavto.pid';
		if (file_exists($pid_file)) {
			$pid = intval(trim(file_get_contents($pid_file)));
			system::kill($pid);
		}
		system::kill('dahuavto/daemon.py');
		system::fuserk(config::byKey('socketport', __CLASS__));
		sleep(1);
	}
   
    public static function deamon_info() {
        $return = array();
		$return['log'] = '';
        $return['launchable'] = 'ok';
        $return['state'] = 'nok';
		$pid_file = jeedom::getTmpFolder(__CLASS__) . '/daemon.pid';
		if (file_exists($pid_file)) {
			if (@posix_getsid(trim(file_get_contents($pid_file)))) {
				$return['state'] = 'ok';
			} else {
				shell_exec('sudo rm -rf ' . $pid_file . ' 2>&1 > /dev/null;rm -rf ' . $pid_file . ' 2>&1 > /dev/null;');
			}
		}
		return $return;
    }


    /*     * *********************Méthodes d'instance************************* */
    public function preSave() {
        $conf = $this->getConfiguration();

        if ($conf['host'] && $conf['username'] && $conf['password'] && !$conf['serial-number']) {
            log::add(__CLASS__, 'info', 'Get device infos... ('. $conf['host'] . ')');

            $ch = curl_init();
            curl_setopt($ch, CURLOPT_URL, "http://" . $conf['host'] . "/cgi-bin/magicBox.cgi?action=getSystemInfo");
            curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
            curl_setopt($ch, CURLOPT_HTTPAUTH, CURLAUTH_DIGEST);
            curl_setopt($ch, CURLOPT_USERPWD, $conf['username'] . ":" . $conf['password']);
            $result = curl_exec($ch);
            log::add(__CLASS__, 'debug', 'Request result : ' . $result);
            if ($result) {
                foreach (explode("\n", $result) as $line) {
                    $infos = explode('=', $line);
                    if (count($infos) == 2) {
                        switch($infos[0]) {
                            case 'deviceType':
                                $this->setConfiguration('device-type', $infos[1]);
                                $this->setConfiguration('model', explode('-', $infos[1])[0]);
                                break;

                            case 'serialNumber':
                                $this->setConfiguration('serial-number', $infos[1]);
                                break;
                        }
                    }
                }
            }
        }
    }

    public function postSave() {
        $calling = $this->getCmd(null, 'calling');
        if (!is_object($calling)) {
            $calling = new dahuavtoCmd();
            $calling->setName(__('Appel', __FILE__));
        }
        $calling->setLogicalId('calling');
        $calling->setEqLogic_id($this->getId());
        $calling->setType('info');
        $calling->setSubType('binary');
        $calling->save();

        $unlocked = $this->getCmd(null, 'unlocked');
        if (!is_object($unlocked)) {
            $unlocked = new dahuavtoCmd();
            $unlocked->setName(__('Porte', __FILE__));
        }
        $unlocked->setLogicalId('unlocked');
        $unlocked->setEqLogic_id($this->getId());
        $unlocked->setType('info');
        $unlocked->setSubType('binary');
        $unlocked->setTemplate('dashboard','lock');
        $unlocked->setTemplate('mobile','lock');
        $unlocked->setDisplay('invertBinary', 1);
        $unlocked->save();

        $unlock = $this->getCmd(null, 'unlock');
        if (!is_object($unlock)) {
            $unlock = new dahuavtoCmd();
            $unlock->setName(__('Déverouiller', __FILE__));
        }
        $unlock->setEqLogic_id($this->getId());
        $unlock->setLogicalId('unlock');
        $unlock->setType('action');
        $unlock->setSubType('other');
        $unlock->save();

        $this->sendToDaemon('add');
    }

    public function preRemove() {
        $this->sendToDaemon('remove');
    }

    public function getPathImgIcon() {
        $model = $this->getConfiguration('model');
        if (!$model) return null;
        return "plugins/dahuavto/plugin_info/" . strtoupper($model) . ".png";
    }

    public function sendToDaemon($command) {
        $conf = $this->getConfiguration();

        if ($conf['host'] && $conf['username'] && $conf['password']) {
            $value = json_encode(array(
                'apikey' => jeedom::getApiKey(__CLASS__),
                'cmd' => $command,
                'device' => array(
                    'id' => $this->getId(),
                    'host' => $conf['host'],
                    'username' => $conf['username'],
                    'password' => $conf['password']
                )
            ));
            self::sendSocketMessage($value,True);
        }
    }

    public static function sendSocketMessage($_value) {
        $socket = socket_create(AF_INET, SOCK_STREAM, 0);
        socket_connect($socket, '127.0.0.1', config::byKey('socketport', __CLASS__));
        socket_write($socket, $_value, strlen($_value));
        socket_close($socket);
	}
}

class dahuavtoCmd extends cmd {
    /*     * *********************Methode d'instance************************* */

  // Exécution d'une commande  
    public function execute($_options = array()) {
        $eqlogic = $this->getEqLogic();

        switch ($this-> getLogicalId()) {
            case 'unlock':
                $conf = $eqlogic->getConfiguration();
                if ($conf['host'] && $conf['username'] && $conf['password']) {
                    log::add(__CLASS__, 'info', 'Unlock door...('. $conf['host'] . ')');
        
                    $ch = curl_init();
                    curl_setopt($ch, CURLOPT_URL, "http://" . $conf['host'] . "/cgi-bin/accessControl.cgi?action=openDoor&channel=1&UserID=101&Type=Remote");
                    curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
                    curl_setopt($ch, CURLOPT_HTTPAUTH, CURLAUTH_DIGEST);
                    curl_setopt($ch, CURLOPT_USERPWD, $conf['username'] . ":" . $conf['password']);
                    $result = curl_exec($ch);
                    if ($result === FALSE) {
                        log::add(__CLASS__, 'error', 'Door open failed');
                    }
                    else {
                        log::add(__CLASS__, 'info', 'Door opened');
                    }
                }

                break;
        }
    }
}


