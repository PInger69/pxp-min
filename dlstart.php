<?php
function start(){
	$event = $_GET['event'];
	if (!@$event)
		return array("success"=>false);
	# make sure it has no : or / \ in the name
	if(strpos($event, '/')!==false || strpos($event, '\\')!==false){
		return array("success"=>False);#invalid name
	}
	#command to start the download
	# create a named pipe for reading the idevcopy output
	# make sure the pipe doesn't exist already
	$pipeName = "/tmp/pxpidevprogress";
	if(file_exists($pipeName))
		unlink($pipeName);
	sleep(2);
	# kill any previous download processes going on
	exec("pgrep idevcopy", $pids);
	if(!empty($pids)){
		$pid = $pids[0];
		// $cmd = "kill `ps ax | grep idevcopy | grep 'grep' -v | awk '{print $1}'` > /dev/null &";
		$cmd = "kill $pid";
		shell_exec($cmd);
	}
	$cmd = "/var/www/html/events/_db/idevcopy ".$event." /var/www/html/events/".$event.' >/dev/null &';
	#successful command will return 0x
	# print cmd
	# os.spawnl(os.P_NOWAIT,self.wwwroot+"_db/idevcopy","/",event,self.wwwroot+event+'/video/main.mp4','>','/dev/null')
	shell_exec($cmd);
	return array("success"=>True);
}
echo(json_encode(start()));
// echo shell_exec("/var/www/html/events/_db/idevcopy ");
?>