PROGRESS_FILE=/tmp/dependancy_dahuavto_in_progress
if [ ! -z $1 ]; then
	PROGRESS_FILE=$1
fi
touch ${PROGRESS_FILE}
echo 0 > ${PROGRESS_FILE}
echo "********************************************************"
echo "*			      Installing dependencies		    	 *"
echo "********************************************************"
sudo apt-get update
echo 30 > ${PROGRESS_FILE}
sudo apt-get install -y python3 python3-pip python3-requests
echo 60 > ${PROGRESS_FILE}
sudo pip3 install requests setuptools pyudev
echo 100 > ${PROGRESS_FILE}
echo "********************************************************"
echo "*	    		 Installation finished  				 *"
echo "********************************************************"
rm ${PROGRESS_FILE}
